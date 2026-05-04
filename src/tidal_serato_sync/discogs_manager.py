import os
import time
import logging
from typing import List, Dict, Optional
from pathlib import Path
from collections import defaultdict
import discogs_client
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DiscogsManager:
    """Manages interactions with the Discogs API for marketplace searches."""

    def __init__(self, env_file: Optional[str] = None):
        """Initialize the DiscogsManager with credentials from .env file.
        
        Args:
            env_file: Optional path to .env file. If not provided, searches in multiple locations.
        """
        # Try to load environment variables from multiple locations
        if env_file:
            # Use specified env file
            env_path = Path(env_file)
            if not env_path.exists():
                raise ValueError(f"El archivo .env especificado no existe: {env_file}")
            load_dotenv(env_path)
            logger.info(f"Credenciales cargadas desde: {env_path}")
        else:
            # Search in multiple locations
            env_locations = [
                Path.cwd() / '.env',  # Current directory
                Path.home() / '.env',  # Home directory  
                Path(__file__).parent.parent.parent / '.env',  # Project root
            ]
            
            loaded = False
            for env_path in env_locations:
                if env_path.exists():
                    load_dotenv(env_path, override=True)
                    loaded = True
                    logger.info(f"Credenciales cargadas desde: {env_path}")
                    break
            
            if not loaded:
                # Try loading from environment without file
                load_dotenv()
        
        self.user_token = os.getenv('DISCOGS_USER_TOKEN')
        self.username = os.getenv('DISCOGS_USERNAME')
        
        if not self.user_token or not self.username:
            if env_file:
                raise ValueError(
                    f"Credenciales de Discogs no encontradas en {env_file}. "
                    "Asegúrate de que DISCOGS_USER_TOKEN y DISCOGS_USERNAME estén definidos."
                )
            else:
                env_locations_str = '\n  - '.join(str(p) for p in env_locations if 'env_locations' in locals())
                raise ValueError(
                    "Credenciales de Discogs no encontradas. "
                    "Asegúrate de que DISCOGS_USER_TOKEN y DISCOGS_USERNAME estén definidos en el archivo .env\n"
                    f"Ubicaciones buscadas:\n  - {env_locations_str}\n\n"
                    "Usa --env-file para especificar una ubicación personalizada."
                )
        
        # Initialize Discogs client
        self.client = discogs_client.Client(
            'SoundMirror/1.5',
            user_token=self.user_token
        )
        
        # Rate limiting: Discogs allows 60 requests per minute for authenticated users
        self.rate_limit_delay = 1.0  # 1 second between requests to be safe
        self.last_request_time = 0
        
        logger.info(f"DiscogsManager initialized for user: {self.username}")

    def _wait_for_rate_limit(self):
        """Ensures we don't exceed Discogs API rate limits."""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last_request
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()

    def search_marketplace(
        self,
        title: str,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        year: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Searches the Discogs marketplace for vinyl records matching the given criteria.
        
        Args:
            title: Track title (required)
            artist: Artist name (optional)
            album: Album name (optional)
            year: Release year (optional)
            limit: Maximum number of results to return (default: 50)
        
        Returns:
            List of dictionaries containing:
                - seller_name: Name of the seller
                - item_title: Full title of the item
                - price: Price with currency
                - condition: Condition of the item (e.g., "Very Good Plus (VG+)")
                - url: URL to the marketplace listing
                - applied_filters: String describing which filters were applied
        """
        self._wait_for_rate_limit()
        
        # Build search query
        query_parts = [title]
        if artist:
            query_parts.insert(0, artist)
        
        query = " ".join(query_parts)
        
        # Build applied filters description
        filters_applied = [f"Title: {title}", "Format: Vinyl"]
        if artist:
            filters_applied.insert(1, f"Artist: {artist}")
        if album:
            filters_applied.append(f"Album: {album}")
        if year:
            filters_applied.append(f"Year: {year}")
        
        filters_str = " | ".join(filters_applied)
        
        logger.info(f"Buscando en Discogs: {query} (filtros: {filters_str})")
        
        results = []
        
        try:
            # Search for releases matching the query
            # Format is always Vinyl as per requirements
            search_params = {
                'type': 'release',
                'format': 'Vinyl',
            }
            
            if artist:
                search_params['artist'] = artist
            if album:
                search_params['release_title'] = album
            if year:
                search_params['year'] = year
            
            # Perform the search
            search_results = self.client.search(query, **search_params)
            
            # Process results and get marketplace listings
            processed_count = 0
            for release in search_results:
                if processed_count >= limit:
                    break
                
                try:
                    # Wait for rate limit before checking marketplace
                    self._wait_for_rate_limit()
                    
                    # Get marketplace listings for this release
                    try:
                        marketplace_stats = release.marketplace_stats
                        if not marketplace_stats:
                            continue
                        
                        # Check if there are any listings for sale
                        num_for_sale = getattr(marketplace_stats, 'num_for_sale', 0)
                        if num_for_sale == 0:
                            continue
                        
                        # Get actual marketplace listings
                        self._wait_for_rate_limit()
                        listings = self.client.search(
                            release_id=release.id,
                            type='release'
                        )
                        
                        # Get marketplace listings through the release
                        for listing in release.marketplace_listings:
                            if processed_count >= limit:
                                break
                            
                            # Only include items that are for sale
                            if listing.status.lower() != 'for sale':
                                continue
                            
                            # Extract listing details
                            seller_name = listing.seller.username if hasattr(listing.seller, 'username') else 'Unknown'
                            item_title = release.title
                            
                            # Format price
                            price_value = getattr(listing.price, 'value', 0)
                            price_currency = getattr(listing.price, 'currency', '')
                            price = f"{price_currency} {price_value:.2f}" if price_value else "N/A"
                            
                            # Get condition
                            condition = listing.condition if hasattr(listing, 'condition') else 'Unknown'
                            
                            # Build URL
                            url = listing.url if hasattr(listing, 'url') else f"https://www.discogs.com/release/{release.id}"
                            
                            results.append({
                                'seller_name': seller_name,
                                'item_title': item_title,
                                'price': price,
                                'condition': condition,
                                'url': url,
                                'applied_filters': filters_str,
                                'release_id': release.id
                            })
                            
                            processed_count += 1
                            
                    except AttributeError:
                        # Some releases may not have marketplace data
                        continue
                    except Exception as e:
                        logger.debug(f"Error processing marketplace for release {release.id}: {e}")
                        continue
                        
                except Exception as e:
                    logger.debug(f"Error processing release: {e}")
                    continue
            
            logger.info(f"Encontrados {len(results)} resultados para '{query}'")
            
        except Exception as e:
            logger.error(f"Error buscando en Discogs: {e}")
        
        return results

    def group_by_seller(self, results: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Groups search results by seller and sorts by number of items available.
        
        Args:
            results: List of marketplace results from search_marketplace()
        
        Returns:
            Dictionary mapping seller_name to list of their items,
            sorted by seller with most items first.
        """
        grouped = defaultdict(list)
        
        for result in results:
            seller = result['seller_name']
            grouped[seller].append(result)
        
        # Sort sellers by number of items (descending)
        sorted_sellers = dict(
            sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True)
        )
        
        return sorted_sellers

    def format_results_table(self, grouped_results: Dict[str, List[Dict]]) -> str:
        """
        Formats grouped results as a readable table.
        
        Args:
            grouped_results: Results grouped by seller from group_by_seller()
        
        Returns:
            Formatted string with table representation
        """
        if not grouped_results:
            return "No se encontraron resultados en Discogs."
        
        output_lines = []
        output_lines.append("\n" + "="*120)
        output_lines.append("RESULTADOS DE BÚSQUEDA EN DISCOGS MARKETPLACE (VINYL)")
        output_lines.append("="*120)
        
        total_items = sum(len(items) for items in grouped_results.values())
        total_sellers = len(grouped_results)
        
        output_lines.append(f"\nTotal: {total_items} items de {total_sellers} vendedores")
        output_lines.append("")
        
        for seller_name, items in grouped_results.items():
            output_lines.append("\n" + "-"*120)
            output_lines.append(f"VENDEDOR: {seller_name} ({len(items)} items disponibles)")
            output_lines.append("-"*120)
            
            # Calculate totals for this seller
            total_price = 0
            currency = None
            
            for item in items:
                price_str = item['price']
                if price_str != "N/A":
                    try:
                        parts = price_str.split()
                        if len(parts) == 2:
                            if currency is None:
                                currency = parts[0]
                            total_price += float(parts[1])
                    except:
                        pass
            
            # Print items
            for i, item in enumerate(items, 1):
                output_lines.append(f"\n  [{i}] {item['item_title']}")
                output_lines.append(f"      Filtros: {item['applied_filters']}")
                output_lines.append(f"      Precio: {item['price']} | Condición: {item['condition']}")
                output_lines.append(f"      URL: {item['url']}")
            
            # Print seller summary
            output_lines.append("")
            if total_price > 0 and currency:
                avg_price = total_price / len(items)
                output_lines.append(f"  RESUMEN: {len(items)} items | Total: {currency} {total_price:.2f} | Promedio: {currency} {avg_price:.2f}")
            else:
                output_lines.append(f"  RESUMEN: {len(items)} items")
        
        output_lines.append("\n" + "="*120 + "\n")
        
        return "\n".join(output_lines)


if __name__ == "__main__":
    # Quick test
    try:
        manager = DiscogsManager()
        results = manager.search_marketplace("Thriller", artist="Michael Jackson", limit=5)
        grouped = manager.group_by_seller(results)
        print(manager.format_results_table(grouped))
    except Exception as e:
        print(f"Error: {e}")
