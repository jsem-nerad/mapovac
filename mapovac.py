import math
import os
import sys
import argparse
import requests
from PIL import Image
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
import questionary

# Load environment variables
load_dotenv()

console = Console()

EARTH_RADIUS = 6378137
EQUATOR_CIRCUMFERENCE = 2 * math.pi * EARTH_RADIUS
TILE_SIZE = 256

def lat_lon_to_pixel(lat, lon, zoom):
    """
    Converts lat/lon to absolute pixel coordinates at a given zoom level.
    Uses Web Mercator projection.
    """
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n * TILE_SIZE
    y = (1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi) / 2.0 * n * TILE_SIZE
    return x, y

def pixel_to_tile(px, py):
    """Converts absolute pixels to tile coordinates and offsets within tile."""
    tx = int(px // TILE_SIZE)
    ty = int(py // TILE_SIZE)
    ox = int(px % TILE_SIZE)
    oy = int(py % TILE_SIZE)
    return tx, ty, ox, oy

def get_tile_width_m(lat, zoom):
    """Returns the width of a tile in meters at a given latitude and zoom."""
    return (EQUATOR_CIRCUMFERENCE * math.cos(math.radians(lat))) / (2.0 ** zoom)

def calculate_best_zoom(lat, target_tiles_per_km):
    """
    Finds the integer zoom level that most closely matches the target resolution.
    target_tiles_per_km = 1000 / target_tile_width_meters
    """
    target_tile_width_m = 1000.0 / target_tiles_per_km
    
    # TileWidth = C * cos(lat) / 2^z
    # 2^z = C * cos(lat) / TileWidth
    # z = log2(C * cos(lat) / TileWidth)
    
    ideal_zoom = math.log2((EQUATOR_CIRCUMFERENCE * math.cos(math.radians(lat))) / target_tile_width_m)
    return max(0, min(20, round(ideal_zoom)))

def download_tile(z, x, y, apikey, mapset="basic"):
    url = f"https://api.mapy.com/v1/maptiles/{mapset}/256/{z}/{x}/{y}?apikey={apikey}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return Image.open(BytesIO(response.content))
    except Exception as e:
        console.print(f"[red]Error downloading tile {z}/{x}/{y}: {e}[/red]")
        return None

def run_tui():
    console.print("[bold blue]Mapy.com Map Downloader[/bold blue]")
    
    try:
        apikey = os.getenv("MAPY_API_KEY")
        if not apikey:
            apikey = questionary.text("Enter your Mapy.com API Key:").ask()
            if apikey is None: sys.exit(0)
        
        lat_str = questionary.text("Enter Latitude (e.g. 50.0755):", default="50.0755").ask()
        if lat_str is None: sys.exit(0)
        lat = float(lat_str)
        
        lon_str = questionary.text("Enter Longitude (e.g. 14.4378):", default="14.4378").ask()
        if lon_str is None: sys.exit(0)
        lon = float(lon_str)
        
        size_str = questionary.text("Enter area size in km (square side):", default="1.0").ask()
        if size_str is None: sys.exit(0)
        size_km = float(size_str)
        
        res_str = questionary.text("Enter resolution (tiles per km):", default="2.0").ask()
        if res_str is None: sys.exit(0)
        res = float(res_str)
        
        output = questionary.text("Output filename:", default="map.png").ask()
        if output is None: sys.exit(0)
        
        return apikey, lat, lon, size_km, res, output
    except KeyboardInterrupt:
        sys.exit(0)
    except ValueError:
        console.print("[red]Invalid input. Please enter numbers for coordinates and size.[/red]")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Mapy.com Map Downloader")
    parser.add_argument("--lat", type=float, help="Latitude")
    parser.add_argument("--lon", type=float, help="Longitude")
    parser.add_argument("--size", type=float, help="Size in km (square side)")
    parser.add_argument("--resolution", type=float, help="Resolution in tiles per km")
    parser.add_argument("--apikey", type=str, help="Mapy.com API Key")
    parser.add_argument("--output", type=str, default="map.png", help="Output filename")
    
    args = parser.parse_args()
    
    if len(sys.argv) == 1:
        apikey, lat, lon, size_km, res, output = run_tui()
    else:
        apikey = args.apikey or os.getenv("MAPY_API_KEY")
        lat = args.lat
        lon = args.lon
        size_km = args.size
        res = args.resolution
        output = args.output
        
        if not all([apikey, lat, lon, size_km, res]):
            parser.print_help()
            sys.exit(1)

    # 1. Calculate Zoom
    zoom = calculate_best_zoom(lat, res)
    tile_width_m = get_tile_width_m(lat, zoom)
    actual_res = 1000.0 / tile_width_m
    
    console.print(f"\n[green]Selected Zoom Level:[/green] {zoom}")
    console.print(f"[green]Actual Resolution:[/green] {actual_res:.2f} tiles/km (Target: {res:.2f})")

    # 2. Calculate pixel dimensions and bounding box
    # Pixel per meter at this lat/zoom
    pixels_per_meter = TILE_SIZE / tile_width_m
    size_px = int(size_km * 1000 * pixels_per_meter)
    
    center_px, center_py = lat_lon_to_pixel(lat, lon, zoom)
    
    left_px = center_px - (size_px / 2)
    top_py = center_py - (size_px / 2)
    right_px = left_px + size_px
    bottom_py = top_py + size_px
    
    # 3. Determine required tiles
    start_tx, start_ty, _, _ = pixel_to_tile(left_px, top_py)
    end_tx, end_ty, _, _ = pixel_to_tile(right_px, bottom_py)
    
    tiles_to_fetch = []
    for tx in range(start_tx, end_tx + 1):
        for ty in range(start_ty, end_ty + 1):
            tiles_to_fetch.append((tx, ty))
            
    console.print(f"[green]Tiles to download:[/green] {len(tiles_to_fetch)} ({end_tx-start_tx+1}x{end_ty-start_ty+1} grid)")

    # 4. Download Tiles
    tile_images = {}
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        task = progress.add_task("Downloading tiles...", total=len(tiles_to_fetch))
        
        def fetch_and_store(coords):
            tx, ty = coords
            img = download_tile(zoom, tx, ty, apikey)
            if img:
                tile_images[(tx, ty)] = img
            progress.update(task, advance=1)

        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(fetch_and_store, tiles_to_fetch)

    # 5. Stitching
    console.print("[yellow]Stitching tiles...[/yellow]")
    full_width = (end_tx - start_tx + 1) * TILE_SIZE
    full_height = (end_ty - start_ty + 1) * TILE_SIZE
    canvas = Image.new("RGB", (full_width, full_height))
    
    for (tx, ty), img in tile_images.items():
        ox = (tx - start_tx) * TILE_SIZE
        oy = (ty - start_ty) * TILE_SIZE
        canvas.paste(img, (ox, oy))
        
    # 6. Precise Cropping
    console.print("[yellow]Cropping to final size...[/yellow]")
    # Offset of our bounding box within the stitched canvas
    crop_left = left_px - (start_tx * TILE_SIZE)
    crop_top = top_py - (start_ty * TILE_SIZE)
    
    # Use round to get the best integer coordinates
    final_image = canvas.crop((
        round(crop_left),
        round(crop_top),
        round(crop_left + size_px),
        round(crop_top + size_px)
    ))
    
    final_image.save(output)
    console.print(f"[bold green]Success![/bold green] Saved map to [cyan]{output}[/cyan] ({size_px}x{size_px} px)")
    console.print("[dim]Note: Mapy.com requires attribution. Please include '© Seznam.cz a.s. a další' when using this image.[/dim]")

if __name__ == "__main__":
    main()
