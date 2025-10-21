import logging
import os
import re

from typing import Tuple, Optional
from pyproj import Transformer
from shapely import wkt as shapely_wkt

from . import requests_get

API_KEY_MAPBS = os.getenv('API_KEY_MAPBS')


# --- CRS helpers --------------------------------------------------------------

_LV95_TO_WGS84 = Transformer.from_crs("EPSG:2056", "EPSG:4326", always_xy=True)

def _is_wgs84_lonlat(x: float, y: float) -> bool:
    """x≈longitude [-180,180], y≈latitude [-90,90]."""
    return -180.0 <= x <= 180.0 and -90.0 <= y <= 90.0

def _is_wgs84_latlon(x: float, y: float) -> bool:
    """x≈latitude [-90,90], y≈longitude [-180,180] (common but reversed)."""
    return -90.0 <= x <= 90.0 and -180.0 <= y <= 180.0

def _is_lv95(e: float, n: float) -> bool:
    return 2_480_000 <= e <= 2_840_000 and 1_075_000 <= n <= 1_296_000

def _is_lv03(e: float, n: float) -> bool:
    return 480_000 <= e <= 840_000 and 70_000 <= n <= 300_000


def _to_wgs84_from_xy(x: float, y: float) -> Tuple[float, float]:
    """
    Detect CRS and return (lon, lat) in WGS84.
    Accepts:
      - WGS84 (lon, lat)
      - WGS84 (lat, lon)  [tolerated]
      - LV95 (EPSG:2056)
      - LV03  (shift to LV95, then to WGS84)
    """
    # Prefer the standard lon/lat interpretation first
    if _is_wgs84_lonlat(x, y):
        return x, y
    if _is_wgs84_latlon(x, y):
        lat, lon = x, y
        return float(lon), float(lat)
    if _is_lv95(x, y):
        lon, lat = _LV95_TO_WGS84.transform(x, y)
        return float(lon), float(lat)
    if _is_lv03(x, y):
        lon, lat = _LV95_TO_WGS84.transform(x + 2_000_000, y + 1_000_000)
        return float(lon), float(lat)

    raise ValueError(f"Coordinates ({x}, {y}) not recognized as WGS84 or Swiss (LV95/LV03).")


# --- WKT helpers --------------------------------------------------------------

def _strip_ewkt_srid(wkt_text: str) -> str:
    """
    Remove a leading 'SRID=xxxx;' if present (EWKT), since shapely.wkt.loads
    may not accept it in all versions.
    """
    wkt_text = wkt_text.strip()
    if wkt_text.upper().startswith("SRID="):
        return wkt_text.split(";", 1)[-1].strip()
    return wkt_text

def _centroid_from_wkt(wkt_text: str) -> Tuple[float, float]:
    """
    Parse WKT and return (x, y) of:
      - the point itself (for POINT)
      - the centroid (for POLYGON, LINESTRING, MULTI*, etc.)
    """
    if not isinstance(wkt_text, str) or not wkt_text.strip():
        raise ValueError("WKT must be a non-empty string.")

    cleaned = _strip_ewkt_srid(wkt_text)
    try:
        geom = shapely_wkt.loads(cleaned)
    except Exception as e:
        raise ValueError(f"Invalid WKT: {e}")

    if geom.is_empty:
        raise ValueError("WKT geometry is empty.")

    # For POINT return the point; else use centroid (covers POLYGON and others)
    g = geom if geom.geom_type.upper() == "POINT" else geom.centroid
    if g.is_empty:
        raise ValueError("Geometry centroid is empty/uncomputable.")

    # Return in geometry coordinate order (X=easting/lon, Y=northing/lat)
    return float(g.x), float(g.y)


# --- Public API ---------------------------------------------------------------

def get_coordinates(street: str, number: str | int) -> tuple[str | None, str | None]:

    def _normalize(street, number) -> str:

        street = street.strip().lower()
        street = street.replace("ß", "ss")
    
        # normalize str. or str at the end
        if street.endswith("str.") or street.endswith("str"):
            street = re.sub(r"str\.?$", "strasse", street)

        number = str(number or "").strip().lower().replace(" ", "")
        return street, number
    def address_exact_match(req_street: str, req_number: str|int,
                        res_street: str, res_number: str|int) -> bool:

        ns_req, nn_req = _normalize(req_street, req_number)
        ns_res, nn_res = _normalize(res_street, res_number)

        return ns_req == ns_res and nn_req == nn_res
    

    def _parse_label(label: str):
        """
        extrac (str, hausnr)
        """
        left = label.split(',', 1)[0].strip()
        m = re.match(r"^(.*\S)\s+(\d+[a-zA-Z]?)$", left)
        if not m:
            return None
        street, number= m.groups()
        return street, number


    # Build the street string and parameters for the API request
    addr_str = f"{street} {number}".strip()
    params = {
        "term": addr_str,
        "maxresults": "1",        
        "partitionlimit": "1",    
        "outputformat": "centroid",  
        "apikey": API_KEY_MAPBS,    
    }

    logging.info(f'get_coordinates: Request started for "{addr_str}".')

    try:
        r = requests_get("https://api.geo.bs.ch/search/v1/search", params=params)
        data = r.json()
    except Exception as e:
        logging.exception(f'get_koordinat: Error fetching/parsing response for "{addr_str}": {e}')
        return None, None

    if not data:
        logging.warning(f'get_koordinat: No results for "{addr_str}".')
        return None, None

    label = data[0].get("label", "")
    res_street, res_number  = _parse_label(label)


    if address_exact_match(street, number, res_street, res_number):
        # Extract the geometry field (expected format: "POINT (x y)")
        point = data[0].get("geom")
        try:
            coords_str = point.replace("POINT (", "").replace(")", "").strip()
            x, y = coords_str.split()
            logging.info(f'get_coordinate: Success for "{addr_str}" → x={x}, y={y}.')
            return x, y
        except Exception as e:
            logging.exception(f'get_coordinate: Error parsing geometry "{point}" for "{addr_str}": {e}')
            return None, None
    logging.warning(f'get_coordinate: No exact match for "{addr_str}"')


def create_navi_link(
    x: str | float | None = None,
    y: str | float | None = None,
    street: Optional[str] = None,
    number: str | int | None = None,
    wkt: Optional[str] = None,
) -> str:
    """
    Create a navigation map link.

    Inputs (priority order):
      1) wkt: a WKT geometry string. If POLYGON (or others), uses centroid.
      2) street + number: geocodes to LV95 (E/N), then converts to WGS84.
      3) x + y: autodetects CRS among:
          - WGS84 (lon, lat)  [preferred]
          - WGS84 (lat, lon)  [tolerated]
          - Swiss LV95 (EPSG:2056)
          - Swiss LV03 (shift to LV95)

    Returns:
      URL string with ?lat=...&lon=... in WGS84.

    Raises:
      ValueError for invalid/missing inputs or unrecognized CRS.
    """

    if all(v is None for v in (x, y, street, number, wkt)):
        raise ValueError("Provide at least one of: wkt, (street+number), or (x,y).")

    # 1) WKT path
    if wkt is not None:
        cx, cy = _centroid_from_wkt(wkt)       # (x, y) in WKT’s CRS
        lon, lat = _to_wgs84_from_xy(cx, cy)   # convert to WGS84
        return f"https://opendatabs.github.io/map-links/?lat={lat}&lon={lon}"

    # 2) Address path
    if street is not None and number is None:
        raise ValueError("If address is provided, number must also be provided.")
    if street:
        # Expected to return LV95 (E, N); adapt if your get_coordinates differs.
        e, n = get_coordinates(street, number)
        if e is None or n is None:
            raise ValueError(f"Could not geocode '{street} {number}'.")
        lon, lat = _to_wgs84_from_xy(float(e), float(n))
        return f"https://opendatabs.github.io/map-links/?lat={lat}&lon={lon}"

    # 3) Raw coordinates path
    if (x is None) ^ (y is None):
        raise ValueError("If one of x or y is provided, the other must be provided as well.")
    x_f, y_f = float(x), float(y)
    lon, lat = _to_wgs84_from_xy(x_f, y_f)

    return f"https://opendatabs.github.io/map-links/?lat={lat}&lon={lon}"
