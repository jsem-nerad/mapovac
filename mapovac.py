import math
import os
import sys
import argparse
import requests
import json
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

BANNER = """
 ██████   ██████                                                            
░░██████ ██████                                                             
 ░███░█████░███   ██████   ████████   ██████  █████ █████  ██████    ██████ 
 ░███░░███ ░███  ░░░░░███ ░░███░░███ ███░░███░░███ ░░███  ░░░░░███  ███░░███
 ░███ ░░░  ░███   ███████  ░███ ░███░███ ░███ ░███  ░███   ███████ ░███ ░░░ 
 ░███      ░███  ███░░███  ░███ ░███░███ ░███ ░░███ ███   ███░░███ ░███  ███
 █████     █████░░████████ ░███████ ░░██████   ░░█████   ░░████████░░██████ 
░░░░░     ░░░░░  ░░░░░░░░  ░███░░░   ░░░░░░     ░░░░░     ░░░░░░░░  ░░░░░░  
                           ░███                                             
                           █████                                            
                          ░░░░░ 
"""

CONFIG_DIR = os.path.expanduser("~/.mapovac")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
CACHE_DIR = os.path.join(CONFIG_DIR, "cache")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_config(config):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f)
    except:
        pass

def download_tile(z, x, y, apikey, mapset="basic"):
    # Cache path: ~/.mapovac/cache/{mapset}/{z}/{x}/{y}.png
    cache_path = os.path.join(CACHE_DIR, mapset, str(z), str(x), f"{y}.png")
    
    # Check cache first
    if os.path.exists(cache_path):
        try:
            return Image.open(cache_path)
        except:
            pass # If file is corrupt, redownload
            
    url = f"https://api.mapy.com/v1/maptiles/{mapset}/256/{z}/{x}/{y}?apikey={apikey}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # Save to cache
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "wb") as f:
            f.write(response.content)
            
        return Image.open(BytesIO(response.content))
    except Exception as e:
        console.print(f"[red]Error downloading tile {z}/{x}/{y}: {e}[/red]")
        return None

def get_apikey(config):
    # 1. Check environment
    apikey = os.getenv("MAPY_API_KEY")
    if apikey:
        return apikey
        
    # 2. Check config
    apikey = config.get("apikey")
    if apikey:
        return apikey
        
    # 3. Prompt user (First run or missing key)
    console.print("[bold yellow]First Run Setup:[/bold yellow] No Mapy.com API Key found.")
    console.print("You can get a free key at [link=https://developer.mapy.com/]developer.mapy.com[/link]\n")
    apikey = questionary.password("Enter your Mapy.com API Key:").ask()
    if not apikey:
        console.print("[red]API Key is required to download tiles.[/red]")
        sys.exit(1)
        
    # Save the key to config immediately
    config["apikey"] = apikey
    save_config(config)
    console.print("[green]API Key saved to config.[/green]\n")
    return apikey

def format_distance(meters):
    if meters >= 1000:
        return f"{meters / 1000:.2f} km"
    return f"{meters:.2f} m"

def run_tui():
    console.print(f"[bold green]{BANNER}[/bold green]")
    console.print("[bold green]Mapy.com Map Downloader[/bold green]\n")
    
    config = load_config()
    apikey = get_apikey(config)
    
    try:
        lat_str = questionary.text("Enter Latitude:", default=str(config.get("lat", "50.0755"))).ask()
        if lat_str is None: sys.exit(0)
        lat = float(lat_str)
        
        lon_str = questionary.text("Enter Longitude:", default=str(config.get("lon", "14.4378"))).ask()
        if lon_str is None: sys.exit(0)
        lon = float(lon_str)
        
        # Consolidate Zoom prompt with a separate display for live feedback
        console.print(f"\n[bold blue]Map scale reference at latitude {lat}:[/bold blue]")
        for z in [0, 5, 10, 15, 18, 20]:
            dist = get_tile_width_m(lat, z)
            console.print(f"  - Zoom {z:>2}: {format_distance(dist)} per tile")
        
        zoom_str = questionary.text(
            "Enter Zoom level (0-20):", 
            default=str(config.get("zoom", "16")),
            validate=lambda val: val.isdigit() and 0 <= int(val) <= 20
        ).ask()
        
        if zoom_str is None: sys.exit(0)
        zoom = int(zoom_str)
        
        # Immediate feedback after selection
        selected_dist = get_tile_width_m(lat, zoom)
        console.print(f"[cyan]Selected scale: {format_distance(selected_dist)} per tile[/cyan]\n")
        
        size_str = questionary.text("Enter map WIDTH in km:", default=str(config.get("size_km", "1.0"))).ask()
        if size_str is None: sys.exit(0)
        size_km = float(size_str)
        
        aspect_choice = questionary.select(
            "Select Aspect Ratio (Width:Height):",
            choices=[
                "Square (1:1)",
                "Digital (16:9)",
                "Digital (4:3)",
                "Photo (3:2)",
                "A4 Portrait (1:1.414)",
                "A4 Landscape (1.414:1)",
                "Custom"
            ],
            default=config.get("aspect_choice", "Square (1:1)")
        ).ask()

        if aspect_choice == "Custom":
            aspect_ratio_str = questionary.text("Enter custom aspect ratio (e.g. 1.777):", default=str(config.get("aspect_ratio", "1.0"))).ask()
            if aspect_ratio_str is None: sys.exit(0)
            aspect_ratio = float(aspect_ratio_str)
        else:
            ratios = {
                "Square (1:1)": 1.0,
                "Digital (16:9)": 16/9,
                "Digital (4:3)": 4/3,
                "Photo (3:2)": 3/2,
                "A4 Portrait (1:1.414)": 1/1.4142,
                "A4 Landscape (1.414:1)": 1.4142
            }
            aspect_ratio = ratios[aspect_choice]

        output = questionary.text("Output filename:", default=config.get("output", "map.png")).ask()
        if output is None: sys.exit(0)
        
        # Save config for next time
        config.update({
            "lat": lat,
            "lon": lon,
            "zoom": zoom,
            "size_km": size_km,
            "aspect_choice": aspect_choice,
            "aspect_ratio": aspect_ratio,
            "output": output
        })
        save_config(config)
        
        return apikey, lat, lon, size_km, zoom, aspect_ratio, output
    except KeyboardInterrupt:
        sys.exit(0)
    except ValueError:
        console.print("[red]Invalid input. Please enter valid numbers.[/red]")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Mapy.com Map Downloader")
    parser.add_argument("--lat", type=float, help="Latitude")
    parser.add_argument("--lon", type=float, help="Longitude")
    parser.add_argument("--size", type=float, help="Width of the map in km")
    parser.add_argument("--zoom", type=int, help="Zoom level (0-20)")
    parser.add_argument("--aspect", type=float, default=1.0, help="Aspect ratio (Width/Height), default 1.0")
    parser.add_argument("--apikey", type=str, help="Mapy.com API Key")
    parser.add_argument("--output", type=str, default="map.png", help="Output filename")
    
    args = parser.parse_args()
    
    if len(sys.argv) == 1:
        apikey, lat, lon, size_km, zoom, aspect_ratio, output = run_tui()
    else:
        apikey = args.apikey or os.getenv("MAPY_API_KEY")
        lat = args.lat
        lon = args.lon
        size_km = args.size
        zoom = args.zoom
        aspect_ratio = args.aspect
        output = args.output
        
        if not all([apikey, lat, lon, size_km, zoom is not None]):
            parser.print_help()
            sys.exit(1)

    # 1. Info Display
    tile_width_m = get_tile_width_m(lat, zoom)
    
    console.print(f"\n[green]Zoom Level:[/green] {zoom}")
    console.print(f"[green]Scale:[/green] {tile_width_m:.2f} meters per tile")

    # 3. Calculate pixel dimensions based on aspect ratio
    # Size_km is now defined as WIDTH
    width_km = size_km
    height_km = width_km / aspect_ratio
    
    pixels_per_meter = TILE_SIZE / tile_width_m
    width_px = int(width_km * 1000 * pixels_per_meter)
    height_px = int(height_km * 1000 * pixels_per_meter)
    
    center_px, center_py = lat_lon_to_pixel(lat, lon, zoom)
    
    left_px = center_px - (width_px / 2)
    top_py = center_py - (height_px / 2)
    right_px = left_px + width_px
    bottom_py = top_py + height_px
    
    # 4. Determine required tiles
    start_tx, start_ty, _, _ = pixel_to_tile(left_px, top_py)
    end_tx, end_ty, _, _ = pixel_to_tile(right_px, bottom_py)
    
    tiles_to_fetch = []
    for tx in range(start_tx, end_tx + 1):
        for ty in range(start_ty, end_ty + 1):
            tiles_to_fetch.append((tx, ty))
            
    console.print(f"[green]Tiles to download:[/green] {len(tiles_to_fetch)} ({end_tx-start_tx+1}x{end_ty-start_ty+1} grid)")

    # 5. Download Tiles
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

    # 6. Stitching
    console.print("[yellow]Stitching tiles...[/yellow]")
    full_width = (end_tx - start_tx + 1) * TILE_SIZE
    full_height = (end_ty - start_ty + 1) * TILE_SIZE
    canvas = Image.new("RGB", (full_width, full_height))
    
    for (tx, ty), img in tile_images.items():
        ox = (tx - start_tx) * TILE_SIZE
        oy = (ty - start_ty) * TILE_SIZE
        canvas.paste(img, (ox, oy))
        
    # 7. Precise Cropping
    console.print("[yellow]Cropping to final size...[/yellow]")
    # Offset of our bounding box within the stitched canvas
    crop_left = left_px - (start_tx * TILE_SIZE)
    crop_top = top_py - (start_ty * TILE_SIZE)
    
    # Use round to get the best integer coordinates
    final_image = canvas.crop((
        round(crop_left),
        round(crop_top),
        round(crop_left + width_px),
        round(crop_top + height_px)
    ))
    
    final_image.save(output)
    console.print(f"[bold green]Success![/bold green] Saved map to [cyan]{output}[/cyan] ({width_px}x{height_px} px)")
    console.print("[dim]Note: Mapy.com requires attribution. Please include '© Seznam.cz a.s. a další' when using this image.[/dim]")

if __name__ == "__main__":
    main()
