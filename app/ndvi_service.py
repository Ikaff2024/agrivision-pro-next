import random
from typing import Dict, Union


def get_ndvi(latitude: float, longitude: float) -> Dict[str, Union[float, str]]:
    """
    Service NDVI simulé — à connecter à Sentinel Hub / Google Earth Engine en production.
    """
    # Simulation d'un appel satellite
    # response = sentinel_hub.fetch_ndvi(lat=latitude, lon=longitude)
    ndvi = round(random.uniform(0.3, 0.9), 2)

    if ndvi > 0.7:
        status = "HEALTHY"
    elif ndvi > 0.5:
        status = "MODERATE"
    else:
        status = "STRESSED"

    return {"ndvi": ndvi, "vegetation_status": status}
