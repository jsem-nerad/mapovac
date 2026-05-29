import math
import os
import sys
import argparse
import requests
import json
import time
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
import questionary
try:
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None

# Load environment variables
load_dotenv()

console = Console()

EARTH_RADIUS = 6378137
EQUATOR_CIRCUMFERENCE = 2 * math.pi * EARTH_RADIUS
TILE_SIZE = 256

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

def get_best_font(size):
    """Attempts to find a system font that supports Czech diacritics."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf", # Fedora
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf"
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    return ImageFont.load_default()

class ConfigManager:
    def __init__(self):
        self.config_dir = os.path.expanduser("~/.mapovac")
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.key_file = os.path.join(self.config_dir, ".secret.key")
        self.cache_dir = os.path.join(self.config_dir, "cache")
        self.fernet = self._setup_encryption()
        self.config = self._load()

    def _setup_encryption(self):
        if not Fernet:
            return None
        
        try:
            if not os.path.exists(self.key_file):
                key = Fernet.generate_key()
                os.makedirs(self.config_dir, exist_ok=True)
                with open(self.key_file, "wb") as f:
                    f.write(key)
                os.chmod(self.key_file, 0o600)
            else:
                with open(self.key_file, "rb") as f:
                    key = f.read()
            return Fernet(key)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not setup encryption: {e}[/yellow]")
            return None

    def _load(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    config = json.load(f)
                    if self.fernet and "apikey_enc" in config:
                        try:
                            config["apikey"] = self.fernet.decrypt(config["apikey_enc"].encode()).decode()
                        except:
                            pass
                    return config
            except:
                pass
        return {}

    def save(self, updates=None):
        if updates:
            self.config.update(updates)
        
        save_data = self.config.copy()
        # Handle apikey encryption
        if self.fernet and "apikey" in save_data:
            save_data["apikey_enc"] = self.fernet.encrypt(save_data["apikey"].encode()).decode()
            # We must NOT delete it from self.config, only from the save_data copy
            save_data.pop("apikey", None)

        try:
            os.makedirs(self.config_dir, exist_ok=True)
            with open(self.config_file, "w") as f:
                json.dump(save_data, f, indent=4)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not save config: {e}[/yellow]")

    def get_apikey(self):
        apikey = os.getenv("MAPY_API_KEY")
        if apikey:
            return apikey
            
        apikey = self.config.get("apikey")
        if apikey:
            return apikey
            
        console.print("[bold yellow]First Run Setup:[/bold yellow] No Mapy.com API Key found.")
        console.print("You can get a free key at [link=https://developer.mapy.com/]developer.mapy.com[/link]\n")
        apikey = questionary.password("Enter your Mapy.com API Key:").ask()
        if not apikey:
            console.print("[red]API Key is required to download tiles.[/red]")
            sys.exit(1)
            
        self.save({"apikey": apikey})
        if self.fernet:
            console.print("[green]API Key saved to config (encrypted).[/green]\n")
        else:
            console.print("[yellow]API Key saved to config (plain text - cryptography not installed).[/yellow]\n")
        return apikey

class TileDownloader:
    def __init__(self, apikey, cache_dir):
        self.apikey = apikey
        self.cache_dir = cache_dir
        self.session = self._setup_session()

    def _setup_session(self):
        session = requests.Session()
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _get_single_tile(self, z, x, y, mapset, retina=False):
        tile_size_str = "256@2x" if retina else "256"
        cache_subdir = f"{mapset}_retina" if retina else mapset
        cache_path = os.path.join(self.cache_dir, cache_subdir, str(z), str(x), f"{y}.png")
        
        if os.path.exists(cache_path):
            try:
                return Image.open(cache_path)
            except:
                pass
                
        url = f"https://api.mapy.com/v1/maptiles/{mapset}/{tile_size_str}/{z}/{x}/{y}?apikey={self.apikey}"
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "wb") as f:
                f.write(response.content)
                
            return Image.open(BytesIO(response.content))
        except Exception as e:
            console.print(f"[red]Error downloading tile {z}/{x}/{y} ({mapset}): {e}[/red]")
            return None

    def download_tile(self, z, x, y, mapset="basic", retina=False):
        if isinstance(mapset, (list, tuple)):
            base_img = None
            for sub_mapset in mapset:
                is_retina_supported = sub_mapset in ["basic", "outdoor"]
                img = self._get_single_tile(z, x, y, sub_mapset, retina=retina if is_retina_supported else False)
                
                if img:
                    if retina and not is_retina_supported:
                        img = img.resize((512, 512), resample=Image.LANCZOS)
                        
                    if base_img is None:
                        base_img = img.convert("RGBA")
                    else:
                        overlay = img.convert("RGBA")
                        base_img.alpha_composite(overlay)
            return base_img.convert("RGB") if base_img else None
        else:
            return self._get_single_tile(z, x, y, mapset, retina=retina)

class MapComposer:
    def __init__(self, downloader):
        self.downloader = downloader

    @staticmethod
    def lat_lon_to_pixel(lat, lon, zoom, tile_size=256):
        lat_rad = math.radians(lat)
        n = 2.0 ** zoom
        x = (lon + 180.0) / 360.0 * n * tile_size
        y = (1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi) / 2.0 * n * tile_size
        return x, y

    @staticmethod
    def pixel_to_tile(px, py, tile_size=256):
        tx = int(px // tile_size)
        ty = int(py // tile_size)
        ox = int(px % tile_size)
        oy = int(py % tile_size)
        return tx, ty, ox, oy

    @staticmethod
    def get_tile_width_m(lat, zoom):
        return (EQUATOR_CIRCUMFERENCE * math.cos(math.radians(lat))) / (2.0 ** zoom)

    def _draw_scale_bar(self, img, lat, zoom, tile_size, position="bottom-left"):
        width_px, height_px = img.size
        draw = ImageDraw.Draw(img, "RGBA")
        
        tile_width_m = self.get_tile_width_m(lat, zoom)
        meters_per_px = tile_width_m / tile_size
        
        target_bar_width_px = width_px * 0.15
        target_meters = target_bar_width_px * meters_per_px
        
        if target_meters < 1:
            nice_dist = 1
        else:
            exp = math.floor(math.log10(target_meters))
            base = target_meters / (10 ** exp)
            if base < 1.5: base = 1
            elif base < 3: base = 2
            elif base < 7: base = 5
            else:
                base = 1
                exp += 1
            nice_dist = base * (10 ** exp)
            
        bar_width_px = int(nice_dist / meters_per_px)
        
        margin = int(width_px * 0.02)
        font_size = max(12, int(height_px * 0.02))
        font = get_best_font(font_size)
        
        text = f"{int(nice_dist)} m" if nice_dist < 1000 else f"{nice_dist/1000} km"
        
        # Calculate text size using a dummy draw or just estimate
        # Pillow 10.0.0+ uses getbbox
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        except:
            tw, th = len(text) * (font_size * 0.6), font_size

        bw, bh = max(bar_width_px, tw) + 20, font_size + 30
        
        if position == "bottom-left":
            bx, by = margin, height_px - margin - bh
        elif position == "bottom-right":
            bx, by = width_px - margin - bw, height_px - margin - bh
        elif position == "top-left":
            bx, by = margin, margin
        elif position == "top-right":
            bx, by = width_px - margin - bw, margin
            
        # Background box (semi-transparent white)
        draw.rectangle([bx, by, bx + bw, by + bh], fill=(255, 255, 255, 160))
        
        # Scale bar line (elegant thin line with ticks)
        lx, ly = bx + 10, by + bh - 15
        draw.line([lx, ly, lx + bar_width_px, ly], fill=(0, 0, 0), width=2)
        # Ticks
        tick_h = 6
        draw.line([lx, ly - tick_h//2, lx, ly + tick_h//2], fill=(0, 0, 0), width=2)
        draw.line([lx + bar_width_px, ly - tick_h//2, lx + bar_width_px, ly + tick_h//2], fill=(0, 0, 0), width=2)
        draw.line([lx + bar_width_px//2, ly - tick_h//2, lx + bar_width_px//2, ly + tick_h//2], fill=(0, 0, 0), width=2)
        
        # Text
        draw.text((lx, ly - 5 - th), text, fill=(0, 0, 0), font=font)

    def _draw_attribution(self, img, position="bottom-right"):
        width_px, height_px = img.size
        draw = ImageDraw.Draw(img, "RGBA")
        text = "© Seznam.cz a.s. a další"
        
        font_size = max(10, int(height_px * 0.015))
        font = get_best_font(font_size)
        
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        except:
            tw, th = len(text) * (font_size * 0.6), font_size
            
        margin = 10
        bw, bh = tw + 10, th + 10
        
        if position == "bottom-left":
            bx, by = margin, height_px - margin - bh
        elif position == "bottom-right":
            bx, by = width_px - margin - bw, height_px - margin - bh
        elif position == "top-left":
            bx, by = margin, margin
        elif position == "top-right":
            bx, by = width_px - margin - bw, margin
            
        # Tiny background for legibility
        draw.rectangle([bx, by, bx + bw, by + bh], fill=(255, 255, 255, 120))
        draw.text((bx + 5, by + 5), text, fill=(0, 0, 0), font=font)

    def compose(self, lat, lon, zoom, width_km, aspect_ratio, mapset, retina=False, output_file="map.png", show_scale=False, scale_pos="bottom-left", show_attribution=False, attr_pos="bottom-right"):
        tile_size = 512 if retina else 256
        tile_width_m = self.get_tile_width_m(lat, zoom)
        
        pixels_per_meter = tile_size / tile_width_m
        width_px = int(width_km * 1000 * pixels_per_meter)
        height_px = int((width_km / aspect_ratio) * 1000 * pixels_per_meter)
        
        total_pixels = width_px * height_px
        if total_pixels > Image.MAX_IMAGE_PIXELS:
            console.print(f"[bold red]Warning:[/bold red] The requested map is very large ({width_px}x{height_px} = {total_pixels/1e6:.1f} MP).")
            if not questionary.confirm("This might use a lot of memory. Do you want to continue?").ask():
                console.print("[yellow]Aborted by user.[/yellow]")
                return False
            Image.MAX_IMAGE_PIXELS = None 

        center_px, center_py = self.lat_lon_to_pixel(lat, lon, zoom, tile_size=tile_size)
        
        left_px = center_px - (width_px / 2)
        top_py = center_py - (height_px / 2)
        right_px = left_px + width_px
        bottom_py = top_py + height_px
        
        start_tx, start_ty, _, _ = self.pixel_to_tile(left_px, top_py, tile_size=tile_size)
        end_tx, end_ty, _, _ = self.pixel_to_tile(right_px, bottom_py, tile_size=tile_size)
        
        tiles_to_fetch = []
        for tx in range(start_tx, end_tx + 1):
            for ty in range(start_ty, end_ty + 1):
                tiles_to_fetch.append((tx, ty))
                
        console.print(f"[green]Tiles to download:[/green] {len(tiles_to_fetch)} ({end_tx-start_tx+1}x{end_ty-start_ty+1} grid)")

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
                img = self.downloader.download_tile(zoom, tx, ty, mapset=mapset, retina=retina)
                if img:
                    tile_images[(tx, ty)] = img
                progress.update(task, advance=1)

            with ThreadPoolExecutor(max_workers=10) as executor:
                executor.map(fetch_and_store, tiles_to_fetch)

        if not tile_images:
            console.print("[red]Failed to download any tiles.[/red]")
            return False

        console.print("[yellow]Stitching tiles...[/yellow]")
        full_width = (end_tx - start_tx + 1) * tile_size
        full_height = (end_ty - start_ty + 1) * tile_size
        canvas = Image.new("RGB", (full_width, full_height))
        
        for (tx, ty), img in tile_images.items():
            ox = (tx - start_tx) * tile_size
            oy = (ty - start_ty) * tile_size
            canvas.paste(img, (ox, oy))
            
        console.print("[yellow]Cropping to final size...[/yellow]")
        crop_left = left_px - (start_tx * tile_size)
        crop_top = top_py - (start_ty * tile_size)
        
        final_image = canvas.crop((
            round(crop_left),
            round(crop_top),
            round(crop_left + width_px),
            round(crop_top + height_px)
        ))
        
        # Add Overlays
        if show_scale:
            self._draw_scale_bar(final_image, lat, zoom, tile_size, position=scale_pos)
        if show_attribution:
            self._draw_attribution(final_image, position=attr_pos)
        
        if output_file.lower().endswith(".pdf"):
            final_image.save(output_file, resolution=300.0)
        else:
            final_image.save(output_file)
        
        console.print(f"[bold green]Success![/bold green] Saved map to [cyan]{output_file}[/cyan] ({width_px}x{height_px} px)")
        console.print("[dim]Note: Mapy.com requires attribution. Please include '© Seznam.cz a.s. a další' when using this image.[/dim]")
        return True

def format_distance(meters):
    if meters >= 1000:
        return f"{meters / 1000:.2f} km"
    return f"{meters:.2f} m"

def run_tui(config_manager):
    console.print(f"[bold green]{BANNER}[/bold green]")
    console.print("[bold green]Mapy.com Map Downloader[/bold green]\n")
    
    config = config_manager.config
    apikey = config_manager.get_apikey()
    
    ASPECT_CHOICES = [
        "Square (1:1)", "Digital (16:9)", "Digital (4:3)", "Photo (3:2)",
        "A4 Portrait (1:1.414)", "A4 Landscape (1.414:1)", "A3 Portrait (1:1.414)", "A3 Landscape (1.414:1)", "Custom"
    ]
    
    try:
        lat = float(questionary.text("Enter Latitude:", default=str(config.get("lat", "50.0755"))).ask() or "50.0755")
        lon = float(questionary.text("Enter Longitude:", default=str(config.get("lon", "14.4378"))).ask() or "14.4378")
        
        mapset_choice = questionary.select(
            "Select Map Layer:",
            choices=["Basic", "Outdoor", "Winter", "Aerial", "Aerial with Labels"],
            default=config.get("mapset_name", "Basic")
        ).ask()
        
        mapset_map = {
            "Basic": "basic", "Outdoor": "outdoor", "Winter": "winter",
            "Aerial": "aerial", "Aerial with Labels": ["aerial", "names-overlay"]
        }
        mapset = mapset_map[mapset_choice]
        
        retina = config.get("retina", False)
        if mapset_choice in ["Basic", "Outdoor", "Aerial with Labels"]:
            retina = questionary.confirm("Use High-DPI (Retina) tiles?", default=retina).ask()

        # Overlays Logic
        overlay_mode = questionary.select(
            "Visual overlays:",
            choices=["Clean map (no overlays)", "Add cartographic overlays (scale bar, attribution)"],
            default="Add cartographic overlays (scale bar, attribution)" if config.get("show_scale") or config.get("show_attribution") else "Clean map (no overlays)"
        ).ask()
        
        show_scale = False
        scale_pos = "bottom-left"
        show_attribution = False
        attr_pos = "bottom-right"
        
        if "cartographic" in overlay_mode:
            show_scale = questionary.confirm("Enable Scale Bar?", default=config.get("show_scale", True)).ask()
            if show_scale:
                scale_pos = questionary.select(
                    "Scale Bar Position:",
                    choices=["bottom-left", "bottom-right", "top-left", "top-right"],
                    default=config.get("scale_pos", "bottom-left")
                ).ask()
                
            show_attribution = questionary.confirm("Enable Attribution Text?", default=config.get("show_attribution", False)).ask()
            if show_attribution:
                attr_pos = questionary.select(
                    "Attribution Position:",
                    choices=["bottom-left", "bottom-right", "top-left", "top-right"],
                    default=config.get("attr_pos", "bottom-right")
                ).ask()

        # Print Presets
        use_preset = questionary.confirm("Use a print-ready preset (A4/A3)?", default=False).ask()
        aspect_ratio = config.get("aspect_ratio", 1.0)
        aspect_choice = config.get("aspect_choice", "Square (1:1)")
        # Ensure aspect_choice is valid for the select prompt later
        if aspect_choice not in ASPECT_CHOICES:
            aspect_choice = "Square (1:1)"

        size_km = config.get("size_km", 1.0)
        
        if use_preset:
            preset = questionary.select(
                "Select Print Preset (300 DPI):",
                choices=["A4 Portrait (1:1.414)", "A4 Landscape (1.414:1)", "A3 Portrait (1:1.414)", "A3 Landscape (1.414:1)"]
            ).ask()
            
            preset_data = {
                "A4 Portrait (1:1.414)": (1/1.4142, 210, 297),
                "A4 Landscape (1.414:1)": (1.4142, 297, 210),
                "A3 Portrait (1:1.414)": (1/1.4142, 297, 420),
                "A3 Landscape (1.414:1)": (1.4142, 420, 297)
            }
            aspect_ratio, width_mm, height_mm = preset_data[preset]
            aspect_choice = preset
            
            pixels_per_mm = 300 / 25.4
            target_width_px = width_mm * pixels_per_mm
            
            console.print(f"[cyan]Target resolution: {int(width_mm * pixels_per_mm)}x{int(height_mm * pixels_per_mm)} px[/cyan]")
            size_km = float(questionary.text("Enter physical width of the area in km:", default=str(size_km)).ask() or "1.0")
            
            tile_size = 512 if retina else 256
            val = (target_width_px * EQUATOR_CIRCUMFERENCE * math.cos(math.radians(lat))) / (size_km * 1000 * tile_size)
            recommended_zoom = round(math.log2(val))
            recommended_zoom = max(0, min(20, recommended_zoom))
            
            console.print(f"[green]Recommended tile zoom for 300 DPI: {recommended_zoom}[/green]")
            zoom = int(questionary.text("Tile zoom level:", default=str(recommended_zoom)).ask() or str(recommended_zoom))
        else:
            console.print(f"\n[bold blue]Map scale reference at latitude {lat}:[/bold blue]")
            for z in [0, 5, 10, 15, 18, 20]:
                dist = MapComposer.get_tile_width_m(lat, z)
                console.print(f"  - Zoom {z:>2}: {format_distance(dist)} per tile")
            
            zoom = int(questionary.text(
                "Enter Tile zoom level (0-20):", 
                default=str(config.get("zoom", "16")),
                validate=lambda val: val.isdigit() and 0 <= int(val) <= 20
            ).ask() or "16")
            
            selected_dist = MapComposer.get_tile_width_m(lat, zoom)
            console.print(f"[cyan]Selected scale: {format_distance(selected_dist)} per tile[/cyan]\n")
            size_km = float(questionary.text("Enter map WIDTH in km:", default=str(size_km)).ask() or "1.0")
            
            aspect_choice = questionary.select(
                "Select Aspect Ratio (Width:Height):",
                choices=ASPECT_CHOICES,
                default=aspect_choice
            ).ask()

            if aspect_choice == "Custom":
                aspect_ratio = float(questionary.text("Enter custom aspect ratio (e.g. 1.777):", default=str(aspect_ratio)).ask() or "1.0")
            else:
                ratios = {
                    "Square (1:1)": 1.0, "Digital (16:9)": 16/9, "Digital (4:3)": 4/3,
                    "Photo (3:2)": 3/2, 
                    "A4 Portrait (1:1.414)": 1/1.4142, "A4 Landscape (1.414:1)": 1.4142,
                    "A3 Portrait (1:1.414)": 1/1.4142, "A3 Landscape (1.414:1)": 1.4142
                }
                aspect_ratio = ratios[aspect_choice]

        output = questionary.text("Output filename (PNG, JPG or PDF):", default=config.get("output", "map.png")).ask() or "map.png"
        
        config_manager.save({
            "lat": lat, "lon": lon, "zoom": zoom, "size_km": size_km,
            "aspect_choice": aspect_choice, "aspect_ratio": aspect_ratio,
            "output": output, "mapset_name": mapset_choice, "retina": retina,
            "show_scale": show_scale, "scale_pos": scale_pos,
            "show_attribution": show_attribution, "attr_pos": attr_pos
        })
        
        return apikey, lat, lon, size_km, zoom, aspect_ratio, output, mapset, retina, show_scale, scale_pos, show_attribution, attr_pos
    except (KeyboardInterrupt, TypeError):
        sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description="Mapy.com Map Downloader")
    parser.add_argument("--lat", type=float, help="Latitude")
    parser.add_argument("--lon", type=float, help="Longitude")
    parser.add_argument("--size", type=float, help="Width of the map in km")
    parser.add_argument("--zoom", type=int, help="Zoom level (0-20)")
    parser.add_argument("--aspect", type=float, default=1.0, help="Aspect ratio (Width/Height)")
    parser.add_argument("--mapset", type=str, default="basic", help="Map layer (basic, outdoor, winter, aerial).")
    parser.add_argument("--retina", action="store_true", help="Use high-DPI tiles (2x resolution)")
    parser.add_argument("--scale", action="store_true", help="Add scale bar")
    parser.add_argument("--scale-pos", type=str, default="bottom-left", help="Scale bar position")
    parser.add_argument("--attribution", action="store_true", help="Add attribution text")
    parser.add_argument("--attr-pos", type=str, default="bottom-right", help="Attribution position")
    parser.add_argument("--apikey", type=str, help="Mapy.com API Key")
    parser.add_argument("--output", type=str, default="map.png", help="Output filename")
    
    args = parser.parse_args()
    config_manager = ConfigManager()
    
    if len(sys.argv) == 1:
        res = run_tui(config_manager)
        if not res: sys.exit(0)
        apikey, lat, lon, size_km, zoom, aspect_ratio, output, mapset, retina, show_scale, scale_pos, show_attribution, attr_pos = res
    else:
        apikey = args.apikey or config_manager.get_apikey()
        lat, lon, size_km, zoom = args.lat, args.lon, args.size, args.zoom
        aspect_ratio, output, mapset, retina = args.aspect, args.output, args.mapset, args.retina
        show_scale, scale_pos = args.scale, args.scale_pos
        show_attribution, attr_pos = args.attribution, args.attr_pos
        if "," in mapset: mapset = mapset.split(",")
        
        if not all([lat, lon, size_km, zoom is not None]):
            parser.print_help()
            sys.exit(1)

    downloader = TileDownloader(apikey, config_manager.cache_dir)
    composer = MapComposer(downloader)
    
    composer.compose(lat, lon, zoom, size_km, aspect_ratio, mapset, retina=retina, output_file=output, 
                     show_scale=show_scale, scale_pos=scale_pos,
                     show_attribution=show_attribution, attr_pos=attr_pos)

if __name__ == "__main__":
    main()
