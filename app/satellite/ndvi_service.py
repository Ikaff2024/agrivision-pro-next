import random
from typing import Dict, Union

def get_ndvi(latitude: float, longitude: float) -> Dict[str, Union[float, str]]:
    """Service NDVI simule — connecter a Sentinel Hub en production."""
    ndvi = round(random.uniform(0.3, 0.9), 2)
    if ndvi > 0.7:
        status = "HEALTHY"
    elif ndvi > 0.5:
        status = "MODERATE"
    else:
        status = "STRESSED"
    return {"ndvi": ndvi, "vegetation_status": status}
