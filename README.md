# Mapovač: Stahování map z Mapy.com

**Mapovač** je CLI nástroj, který umožňuje generovat kvalitní, na míru oříznuté mapové snímky s využitím API Mapy.com.

```text
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
```

## Hlavní funkce

- **Přesné měřítko:** Nastavte si úroveň přiblížení (zoom 0–20) a získejte okamžitou informaci o fyzické velikosti (metry na dlaždici) pro danou zeměpisnou šířku.
- **Vysoké rozlišení (Retina):** Podpora `@2x` dlaždic pro extrémně ostré mapy vhodné pro tisk.
- **Tiskové předvolby:** Snadné generování map ve formátech A4/A3 s automatickým výpočtem ideálního přiblížení pro 300 DPI.
- **Kartografické doplňky:** Volitelná měřítková lišta a tiráž (citace) přímo v obrázku.
- **Export do PDF:** Podpora ukládání přímo do PDF pro snadný tisk.
- **Zabezpečení:** API klíč je v konfiguračním souboru uložen šifrovaně.
- **Robustní stahování:** Automatické opakování pokusů (retry) při výpadku sítě.
- **Caching:** Stažené dlaždice se ukládají do složky `~/.mapovac/cache/`.

## Instalace

1. **Klonování repozitáře:**
   ```bash
   git clone <repo-url>
   cd mapovac
   ```

2. **Příprava prostředí:**
   ```bash
   python3 -m venv venv
   ./venv/bin/pip install -r requirements.txt
   ```

##  Použití

### Interaktivní režim (TUI)
Stačí spustit skript bez parametrů. Program vás provede nastavením:
```bash
./venv/bin/python3 mapovac.py
```

### Automatizovaný režim (CLI)
Pro rychlé spuštění s konkrétními parametry:
```bash
./venv/bin/python3 mapovac.py --lat 50.0755 --lon 14.4378 --size 2 --zoom 16 --aspect 1.777 --retina --output praha.png
```
*Argumenty:*
- `--lat`, `--lon`: Souřadnice středu mapy.
- `--size`: Šířka mapy v kilometrech.
- `--zoom`: Úroveň přiblížení dlaždic (0-20).
- `--aspect`: Poměr stran (šířka/výška).
- `--retina`: Použít dlaždice ve vysokém rozlišení (2x).
- `--scale`: Přidat měřítkovou lištu.
- `--scale-pos`: Pozice lišty (`bottom-left`, `bottom-right`, `top-left`, `top-right`).
- `--attribution`: Přidat tiráž (citaci).
- `--attr-pos`: Pozice tiráže.
- `--output`: Název výsledného souboru.

## API Klíč

Pro fungování aplikace potřebujete API klíč od Seznam.cz. Můžete ho získat zdarma na [developer.mapy.com](https://developer.mapy.com/).
Aplikace se vás na něj zeptá při prvním spuštění a uloží ho do `~/.mapovac/config.json`.

## ⚖️ Licence a citace

Tento nástroj využívá dlaždice Mapy.com. Při používání výsledných snímků prosím dodržujte podmínky Seznam.cz a uvádějte povinnou citaci:
> **© Seznam.cz a.s. a další**
