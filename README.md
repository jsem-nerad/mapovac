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
- **Flexibilní formáty:** Podpora různých poměrů stran – od čtverce až po 16:9 nebo tiskový formát A4 (nebo vlastní poměr stran).
- **Caching:** Stažené dlaždice se ukládají do složky `~/.mapovac/cache/`, takže opakované generování stejné oblasti nespotřebuje žádné kredity.
- **Trvalé nastavení:** Nástroj si pamatuje vaše poslední zadané hodnoty (souřadnice, zoom, API klíč), takže při dalším spuštění stačí jen potvrzovat klávesou Enter.
- **TUI i CLI režim:** Interaktivní rozhraní pro lidi a parametry příkazové řádky pro automatizaci.

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
./venv/bin/python3 mapovac.py --lat 50.0755 --lon 14.4378 --size 2 --zoom 16 --aspect 1.777 --output praha.png
```
*Argumenty:*
- `--lat`, `--lon`: Souřadnice středu mapy.
- `--size`: Šířka mapy v kilometrech.
- `--zoom`: Úroveň přiblížení (0-20).
- `--aspect`: Poměr stran (šířka/výška).
- `--output`: Název výsledného souboru.

## API Klíč

Pro fungování aplikace potřebujete API klíč od Seznam.cz. Můžete ho získat zdarma na [developer.mapy.com](https://developer.mapy.com/).
Aplikace se vás na něj zeptá při prvním spuštění a uloží ho do `~/.mapovac/config.json`.

## ⚖️ Licence a citace

Tento nástroj využívá dlaždice Mapy.com. Při používání výsledných snímků prosím dodržujte podmínky Seznam.cz a uvádějte povinnou citaci:
> **© Seznam.cz a.s. a další**
