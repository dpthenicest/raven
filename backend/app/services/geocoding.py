"""Geocoding service for feeders using Google Maps API."""
import httpx
from datetime import datetime
from typing import Optional, Dict, Any, List
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.shape import from_shape
from shapely.geometry import box

from app.core.config import settings
from app.models.feeder import Feeder
from app.utils.data_cleaner import DataCleaner


class GeocodingService:
    """Service for geocoding feeders using Google Maps API."""
    
    BASE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
    
    def __init__(self):
        self.data_cleaner = DataCleaner()
    
    def build_address(self, feeder: Feeder) -> str:
        """
        Construct a geocoding-ready address string from feeder name and state.
        
        Example: "Ajah, Lagos, Nigeria"
        """
        # Clean the feeder name before building address
        clean_name = self.data_cleaner.clean_feeder_name(feeder.name)
        
        parts = [clean_name, feeder.state, "Nigeria"]
        return ", ".join([p for p in parts if p])
    
    @staticmethod
    async def geocode_address(address: str) -> Optional[Dict[str, Any]]:
        """
        Call Google Maps Geocoding API to retrieve coordinates.
        
        Returns a dictionary with latitude, longitude, place_id, bounds (if available),
        and formatted_address.
        """
        if not settings.GOOGLE_MAPS_API_KEY:
            logger.error("GOOGLE_MAPS_API_KEY not configured")
            return None
        
        params = {
            "address": address,
            "key": settings.GOOGLE_MAPS_API_KEY
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(GeocodingService.BASE_URL, params=params)
                
                if response.status_code != 200:
                    logger.error(f"Geocoding API error ({response.status_code}): {response.text}")
                    return None
                
                data = response.json()
                
                if data.get("status") != "OK" or not data.get("results"):
                    logger.warning(f"Geocoding failed for {address}: {data.get('status')}")
                    return None
                
                result = data["results"][0]
                geometry = result.get("geometry", {})
                
                # Safely extract coordinates and bounds
                location = geometry.get("location", {})
                bounds = geometry.get("bounds") or geometry.get("viewport")
                
                return {
                    "latitude": location.get("lat"),
                    "longitude": location.get("lng"),
                    "place_id": result.get("place_id"),
                    "formatted_address": result.get("formatted_address"),
                    "bounds": bounds,  # may be None if missing
                }
        except Exception as e:
            logger.error(f"Error geocoding address '{address}': {e}", exc_info=True)
            return None
    
    @staticmethod
    def bounds_to_polygon(bounds: Dict[str, Any]) -> Optional[Any]:
        """
        Convert Google Maps bounds to PostGIS polygon geometry.
        
        Args:
            bounds: Dictionary with 'northeast' and 'southwest' keys containing lat/lng
            
        Returns:
            GeoAlchemy2 geometry object or None
        """
        if not bounds:
            return None
        
        try:
            northeast = bounds.get("northeast", {})
            southwest = bounds.get("southwest", {})
            
            ne_lat = northeast.get("lat")
            ne_lng = northeast.get("lng")
            sw_lat = southwest.get("lat")
            sw_lng = southwest.get("lng")
            
            if None in (ne_lat, ne_lng, sw_lat, sw_lng):
                return None
            
            # Create a box polygon from bounds
            polygon = box(sw_lng, sw_lat, ne_lng, ne_lat)
            return from_shape(polygon, srid=4326)
        except Exception as e:
            logger.error(f"Error converting bounds to polygon: {e}")
            return None
    
    @staticmethod
    async def geocode_feeder(db: AsyncSession, feeder: Feeder) -> bool:
        """
        Geocode a single feeder and update its location fields.
        
        Returns True if successful, False otherwise.
        """
        service = GeocodingService()
        address = service.build_address(feeder)
        logger.info(f"Geocoding feeder: {feeder.name} ({feeder.id}) with address: {address}")
        
        geo_data = await GeocodingService.geocode_address(address)
        
        if not geo_data:
            logger.warning(f"Could not geocode feeder: {feeder.name}")
            return False
        
        # Update feeder with geocoding results
        feeder.latitude = geo_data.get("latitude")
        feeder.longitude = geo_data.get("longitude")
        feeder.formatted_address = geo_data.get("formatted_address")
        
        # Convert bounds to PostGIS polygon
        if geo_data.get("bounds"):
            feeder.bounds = GeocodingService.bounds_to_polygon(geo_data["bounds"])
        
        logger.info(
            f"✅ Geocoded feeder: {feeder.name} - "
            f"Lat: {feeder.latitude}, Lng: {feeder.longitude}"
        )
        
        return True
    
    @staticmethod
    async def geocode_all_feeders(db: AsyncSession) -> Dict[str, Any]:
        """
        Geocode all feeders in the database.
        
        Returns statistics about the geocoding process.
        """
        logger.info("🌍 Starting geocoding for ALL feeders...")
        
        # Get all feeders
        result = await db.execute(select(Feeder))
        feeders = result.scalars().all()
        
        total = len(feeders)
        logger.info(f"📦 Found {total} total feeders")
        
        processed = 0
        skipped = 0
        failed = 0
        
        for i, feeder in enumerate(feeders, start=1):
            logger.info(f"\n➡️ [{i}/{total}] Processing: {feeder.name}")
            
            try:
                success = await GeocodingService.geocode_feeder(db, feeder)
                
                if success:
                    processed += 1
                else:
                    failed += 1
                    
            except Exception as e:
                logger.error(f"Error processing feeder {feeder.name}: {e}", exc_info=True)
                failed += 1
        
        # Commit all changes
        await db.commit()
        
        logger.info(f"\n🎯 Geocoding completed for ALL feeders")
        logger.info(f"   ✅ Successfully processed: {processed}")
        logger.info(f"   ❌ Failed: {failed}")
        logger.info(f"   🧾 Total: {total}")
        
        return {
            "total": total,
            "processed": processed,
            "failed": failed,
            "message": f"Geocoded {processed} out of {total} feeders"
        }
    
    @staticmethod
    async def geocode_feeders_by_disco(
        db: AsyncSession, 
        disco_code: str
    ) -> Dict[str, Any]:
        """
        Geocode all feeders for a specific disco.
        
        Returns statistics about the geocoding process.
        """
        logger.info(f"🔍 Starting geocoding for disco: {disco_code}")
        
        # Get feeders for this disco
        result = await db.execute(
            select(Feeder).where(Feeder.disco_code == disco_code)
        )
        feeders = result.scalars().all()
        
        total = len(feeders)
        logger.info(f"📍 Found {total} feeders for disco '{disco_code}'")
        
        if total == 0:
            return {
                "disco_code": disco_code,
                "total": 0,
                "processed": 0,
                "failed": 0,
                "message": f"No feeders found for disco '{disco_code}'"
            }
        
        processed = 0
        failed = 0
        
        for i, feeder in enumerate(feeders, start=1):
            logger.info(f"\n➡️ [{i}/{total}] Processing: {feeder.name}")
            
            try:
                success = await GeocodingService.geocode_feeder(db, feeder)
                
                if success:
                    processed += 1
                else:
                    failed += 1
                    
            except Exception as e:
                logger.error(f"Error processing feeder {feeder.name}: {e}", exc_info=True)
                failed += 1
        
        # Commit all changes
        await db.commit()
        
        logger.info(f"\n🎯 Geocoding completed for disco '{disco_code}'")
        logger.info(f"   ✅ Successfully processed: {processed}")
        logger.info(f"   ❌ Failed: {failed}")
        logger.info(f"   🧾 Total: {total}")
        
        return {
            "disco_code": disco_code,
            "total": total,
            "processed": processed,
            "failed": failed,
            "message": f"Geocoded {processed} out of {total} feeders for {disco_code}"
        }
