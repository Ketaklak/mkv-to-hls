# main.py — MKV → HLS (1080p/720p/480p) NVENC + UI Rich + I18N + choix TS/M4S (invite)
# Windows/macOS/Linux — nécessite FFmpeg avec h264_nvenc. GPU scale via scale_cuda si dispo (+ hwupload_cuda).
# Audio : priorité VFF > VFI > VF générique > VFA > VFQ > autres. 1ʳᵉ piste audio = default.

import json
import os
import re
import subprocess
import locale
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Any

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    Progress, BarColumn, TimeRemainingColumn, TimeElapsedColumn,
    TaskProgressColumn, SpinnerColumn, TextColumn
)
from rich.table import Table
from rich.theme import Theme

# ==========================
# CONFIG
# ==========================
RESOLUTIONS: List[Tuple[str, str, str, int]] = [
    ("1080p", "1920:1080", "1920x1080", 7000),
    ("720p",  "1280:720",  "1280x720",  4000),
    ("480p",  "854:480",   "854x480",   2000),
]
INPUT_DIR = "input"          # Dossier d'entrée à scanner (récursif)
OUTPUT_DIR = "output"        # Dossier racine de sortie
SCAN_DIR = INPUT_DIR         # (compat si utilisé ailleurs)
DELETE_SOURCE = False        # Supprimer le MKV après succès ?
AUDIO_BITRATE_K = 128        # kbps par piste audio
SEG_DUR = 10                 # durée segment HLS (s) — VOD recommandé
GOP_SECONDS = 10.0           # GOP aligné aux segments (keyframe toutes les 10 s)
SOFT_SCALE_IF_NEEDED = True  # Si scale CUDA indispo/échoue → scale CPU, encodage NVENC conservé

# ==========================
# I18N
# ==========================
TRANSLATIONS = {
    "en": {
        "app_title": "MKV → HLS NVENC",
        "files_title": "File Queue",
        "col_num": "#",
        "col_file": "File",
        "col_dur": "Duration",
        "col_langs": "Audio Langs",
        "col_status": "Status",
        "no_mkv": "No .mkv files found.",
        "nvenc_missing": "NVENC (h264_nvenc) is not available in your FFmpeg build. Install a build with NVENC (e.g., Gyan, BtbN).",
        "cuda_filters_on": "CUDA filters detected → scale_cuda enabled.",
        "cuda_filters_off": "CUDA filters not found → using CPU scale; NVENC (GPU) encoder is preserved.",
        "cuda_filters_required": "CUDA filters missing and SOFT_SCALE_IF_NEEDED=False.",
        "file_task": "File",
        "fallback_cpu": "{name} → {res} : falling back to CPU scale.",
        "ok_variant": "{name} → {res} OK",
        "master_done": "Master → {path}",
        "done": "Done. Check 1080p/720p/480p folders and master.m3u8.",
        "error": "ERROR",
        "pending": "pending",
        "scanning": "scanning",
        "ask_mode": "HLS mode?\n  1 = TS (.ts segments)\n  2 = fMP4 (.m4s segments)\nChoice: ",
        "ask_mode_invalid": "Please type 1 (TS) or 2 (fMP4).",
        "mode_name_ts": "TS",
        "mode_name_fmp4": "fMP4",
    },
    "fr": {
        "app_title": "MKV → HLS NVENC",
        "files_title": "File Queue",
        "col_num": "#",
        "col_file": "Fichier",
        "col_dur": "Durée",
        "col_langs": "Langues audio",
        "col_status": "Statut",
        "no_mkv": "Aucun fichier .mkv trouvé.",
        "nvenc_missing": "NVENC (h264_nvenc) indisponible dans ta build FFmpeg. Installe une build avec NVENC (Gyan, BtbN, etc.).",
        "cuda_filters_on": "Filtres CUDA détectés → scale_cuda actif.",
        "cuda_filters_off": "Filtres CUDA absents → scale CPU, encodage NVENC (GPU) conservé.",
        "cuda_filters_required": "Filtres CUDA absents et SOFT_SCALE_IF_NEEDED=False.",
        "file_task": "Fichier",
        "fallback_cpu": "{name} → {res} : fallback en scale CPU.",
        "ok_variant": "{name} → {res} OK",
        "master_done": "Master → {path}",
        "done": "Terminé. Vérifie les dossiers 1080p/720p/480p et master.m3u8.",
        "error": "ERREUR",
        "pending": "en attente",
        "scanning": "scan",
        "ask_mode": "Mode HLS ?\n  1 = TS (.ts)\n  2 = fMP4 (.m4s)\nChoix : ",
        "ask_mode_invalid": "Tape 1 (TS) ou 2 (fMP4).",
        "mode_name_ts": "TS",
        "mode_name_fmp4": "fMP4",
    },
    "es": {
        "app_title": "MKV → HLS NVENC",
        "files_title": "Cola de archivos",
        "col_num": "#",
        "col_file": "Archivo",
        "col_dur": "Duración",
        "col_langs": "Idiomas audio",
        "col_status": "Estado",
        "no_mkv": "No se encontraron archivos .mkv.",
        "nvenc_missing": "NVENC (h264_nvenc) no está disponible en tu FFmpeg. Instala una build con NVENC (Gyan, BtbN).",
        "cuda_filters_on": "Filtros CUDA detectados → scale_cuda activado.",
        "cuda_filters_off": "Sin filtros CUDA → escala CPU; el codificador NVENC (GPU) se mantiene.",
        "cuda_filters_required": "Faltan filtros CUDA y SOFT_SCALE_IF_NEEDED=False.",
        "file_task": "Archivo",
        "fallback_cpu": "{name} → {res} : cambio a escalado por CPU.",
        "ok_variant": "{name} → {res} OK",
        "master_done": "Master → {path}",
        "done": "Listo. Revisa las carpetas 1080p/720p/480p y master.m3u8.",
        "error": "ERROR",
        "pending": "pendiente",
        "scanning": "escaneando",
        "ask_mode": "¿Modo HLS?\n  1 = TS (.ts)\n  2 = fMP4 (.m4s)\nOpción: ",
        "ask_mode_invalid": "Escribe 1 (TS) o 2 (fMP4).",
        "mode_name_ts": "TS",
        "mode_name_fmp4": "fMP4",
    },
    "de": {
        "app_title": "MKV → HLS NVENC",
        "files_title": "Dateiwarteschlange",
        "col_num": "#",
        "col_file": "Datei",
        "col_dur": "Dauer",
        "col_langs": "Audiosprachen",
        "col_status": "Status",
        "no_mkv": "Keine .mkv-Dateien gefunden.",
        "nvenc_missing": "NVENC (h264_nvenc) ist in deiner FFmpeg-Build nicht verfügbar. Installiere eine Build mit NVENC (Gyan, BtbN).",
        "cuda_filters_on": "CUDA-Filter erkannt → scale_cuda aktiv.",
        "cuda_filters_off": "CUDA-Filter fehlen → CPU-Scaling; NVENC (GPU) bleibt erhalten.",
        "cuda_filters_required": "CUDA-Filter fehlen und SOFT_SCALE_IF_NEEDED=False.",
        "file_task": "Datei",
        "fallback_cpu": "{name} → {res} : Fallback auf CPU-Skalierung.",
        "ok_variant": "{name} → {res} OK",
        "master_done": "Master → {path}",
        "done": "Fertig. Prüfe 1080p/720p/480p Ordner und master.m3u8.",
        "error": "FEHLER",
        "pending": "wartend",
        "scanning": "scan",
        "ask_mode": "HLS-Modus?\n  1 = TS (.ts)\n  2 = fMP4 (.m4s)\nAuswahl: ",
        "ask_mode_invalid": "Bitte 1 (TS) oder 2 (fMP4) eingeben.",
        "mode_name_ts": "TS",
        "mode_name_fmp4": "fMP4",
    },
}

def detect_lang() -> str:
    # ENV overrides
    for var in ("APP_LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(var)
        if v:
            code = v.split(".")[0].split("_")[0].lower()
            if code in TRANSLATIONS:
                return code
    # locale fallback
    try:
        try:
            locale.setlocale(locale.LC_CTYPE, "")
        except Exception:
            pass
        loc = locale.getlocale()[0] or ""
    except Exception:
        loc = ""
    if not loc:
        try:
            loc = locale.getdefaultlocale()[0] or ""
        except Exception:
            loc = ""
    code = (loc.split("_")[0].lower() if loc else "en")
    return code if code in TRANSLATIONS else "en"

LANG = detect_lang()

def t(key: str, **kwargs) -> str:
    table = TRANSLATIONS.get(LANG, TRANSLATIONS["en"])
    base = table.get(key, TRANSLATIONS["en"].get(key, key))
    return base.format(**kwargs) if kwargs else base

# ==========================
# UI
# ==========================
console = Console(theme=Theme({
    "ok": "bold green",
    "warn": "yellow",
    "err": "bold red",
    "info": "cyan",
    "title": "bold white",
}))

def log_ok(msg): console.print(f"[ok] {msg}")
def log_warn(msg): console.print(f"[warn] {msg}")
def log_err(msg): console.print(f"[err] {msg}")
def log_info(msg): console.print(f"[info] {msg}")

# ==========================
# FFPROBE & CHECKS
# ==========================

def run_check_output(args: List[str]) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)

def ffprobe_json(path: Path) -> dict:
    args = ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    out = run_check_output(args)
    return json.loads(out)

def detect_nvenc_available() -> bool:
    try:
        out = run_check_output(["ffmpeg", "-hide_banner", "-encoders"])
        return "h264_nvenc" in out
    except Exception:
        return False

def detect_scale_cuda_available() -> bool:
    try:
        out = run_check_output(["ffmpeg", "-hide_banner", "-filters"])
        return ("scale_cuda" in out) or ("scale_npp" in out)
    except Exception:
        return False

def get_video_fps_and_duration(info: dict) -> tuple[float, float]:
    streams = info.get("streams", [])
    duration = 0.0
    fps = 25.0
    fmt = info.get("format", {})
    if "duration" in fmt:
        try:
            duration = float(fmt["duration"])
        except:
            duration = 0.0
    for s in streams:
        if s.get("codec_type") == "video":
            afr = s.get("avg_frame_rate") or s.get("r_frame_rate")
            if afr and afr != "0/0":
                try:
                    num, den = afr.split("/")
                    num = float(num)
                    den = float(den)
                    if den != 0:
                        fps = num / den
                except:
                    pass
    return fps, duration

# --------- Audio helpers (priorité VFF > VFI > VF > VFA > VFQ) ----------
FRENCH_LANG_CODES = {"fre", "fra", "fr"}
KW_VFF = {"vff"}
KW_VFI = {"vfi"}
KW_VFQ = {"vfq", "québec", "quebec"}
KW_VFA = {"vfa"}
KW_FR_GENERIC = {"vf", "french", "français", "francais"}

def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()

def _has_word(s: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", s) is not None

def _contains_any(s: str, words: set[str], word_boundary: bool = True) -> bool:
    if word_boundary:
        return any(_has_word(s, w) for w in words)
    return any(w in s for w in words)

def _classify_fr_variant(lang_norm: str, title: str, handler: str) -> tuple[bool, int]:
    s = " ".join([lang_norm, title, handler]).lower()
    is_fr = (
        lang_norm in FRENCH_LANG_CODES or
        _contains_any(s, KW_FR_GENERIC, word_boundary=True) or
        _contains_any(s, KW_VFF, word_boundary=True) or
        _contains_any(s, KW_VFI, word_boundary=True) or
        _contains_any(s, KW_VFA, word_boundary=True) or
        _contains_any(s, KW_VFQ, word_boundary=True)
    )
    if not is_fr:
        return False, 999
    is_vff = _contains_any(s, KW_VFF, word_boundary=True)
    is_vfi = _contains_any(s, KW_VFI, word_boundary=True)
    is_vfa = _contains_any(s, KW_VFA, word_boundary=True)
    is_vfq = _contains_any(s, KW_VFQ, word_boundary=True) or (
        (" qc" in s or "(qc" in s or "[qc" in s) and _contains_any(s, {"vf"}, word_boundary=True)
    )
    if is_vff:
        return True, 0
    if is_vfi:
        return True, 1
    if is_vfa:
        return True, 3
    if is_vfq:
        return True, 4
    return True, 2  # VF générique

def get_ordered_audio_map(info: dict) -> List[Tuple[int, str]]:
    audio_list: List[Dict[str, Any]] = []
    audio_pos = 0
    for s in info.get("streams", []):
        if s.get("codec_type") != "audio":
            continue
        tags = s.get("tags", {}) or {}
        lang_raw = _norm(tags.get("language") or tags.get("LANGUAGE"))
        title_raw = _norm(tags.get("title") or tags.get("TITLE"))
        handler_raw = _norm(tags.get("handler_name") or tags.get("HANDLER_NAME"))
        if lang_raw in {"eng", "en", "english"}:
            lang_norm = "eng"
        elif lang_raw in {"fre", "fra", "fr", "french", "français", "francais"}:
            lang_norm = "fre"
        elif lang_raw:
            lang_norm = lang_raw
        else:
            is_fr, _ = _classify_fr_variant("und", title_raw, handler_raw)
            lang_norm = "fre" if is_fr else "und"
        is_fr, score_fr = _classify_fr_variant(lang_norm, title_raw, handler_raw)
        audio_list.append({
            "pos": audio_pos,
            "lang": lang_norm,
            "is_fr": is_fr,
            "score": score_fr,
            "orig": len(audio_list),
        })
        audio_pos += 1
    audio_list.sort(key=lambda x: (0 if x["is_fr"] else 1, x["score"], x["orig"]))
    return [(a["pos"], a["lang"]) for a in audio_list]

# ==========================
# ENCODING
# ==========================

def build_ffmpeg_cmd(
    src: Path,
    out_playlist: Path,
    out_segments_pattern: Path,
    scale_str: str,
    v_bitrate_k: int,
    gop: int,
    audio_map: List[Tuple[int, str]],
    use_cuda_scale: bool,
    mode: str,  # "ts" | "fmp4"
) -> List[str]:
    w, h = scale_str.split(":")
    args = [
        "ffmpeg", "-hide_banner", "-y",
        "-nostats",
        "-progress", "pipe:1",
        "-loglevel", "error",
        "-i", str(src),
        "-c:v", "h264_nvenc",
        "-preset", "p4", "-tune", "hq", "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-b:v", f"{v_bitrate_k}k", "-maxrate", f"{v_bitrate_k}k", "-bufsize", f"{v_bitrate_k*2}k",
        "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0",
        "-c:a", "aac", "-b:a", f"{AUDIO_BITRATE_K}k", "-ac", "2",
    ]
    if use_cuda_scale:
        args += ["-vf", f"hwupload_cuda,scale_cuda={w}:{h}:interp_algo=lanczos"]
    else:
        args += ["-vf", f"scale={w}:{h}:flags=lanczos"]

    # map video + audios
    args += ["-map", "0:v:0"]
    for pos, _lang in audio_map:
        args += ["-map", f"0:a:{pos}"]

    # set languages metadata in same order
    for out_idx, (_pos, lang) in enumerate(audio_map):
        args += [f"-metadata:s:a:{out_idx}", f"language={lang}"]

    # mark first audio as default
    if audio_map:
        args += ["-disposition:a:0", "default"]

    # HLS muxer
    args += [
        "-f", "hls",
        "-hls_time", str(SEG_DUR),
        "-hls_playlist_type", "vod",
        "-hls_list_size", "0",
    ]

    if mode == "fmp4":
        # init.mp4 + segments à côté de la playlist (via cwd)
        args += [
            "-hls_flags", "independent_segments+split_by_time",
            "-hls_segment_type", "fmp4",
            "-hls_fmp4_init_filename", "init.mp4",
            "-hls_segment_filename", str(out_segments_pattern).replace("%03d.ts", "%03d.m4s"),
        ]
    else:
        args += [
            "-hls_flags", "independent_segments",
            "-hls_segment_filename", str(out_segments_pattern),
        ]

    args += [str(out_playlist)]
    return args

def run_ffmpeg_with_progress(args: List[str], total_seconds: float, task_id, progress: Progress, cwd: Optional[Path] = None):
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, cwd=str(cwd) if cwd else None)
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            if line.startswith("out_time_ms="):
                ms = int(line.split("=", 1)[1])
                seconds = ms / 1_000_000.0
                if total_seconds > 0:
                    progress.update(task_id, completed=min(seconds, total_seconds))
            elif line.startswith("speed="):
                sp = line.split("=", 1)[1]
                progress.update(task_id, description=f"[white]Encodage[/] @ {sp}")
            elif line.startswith("progress=") and line.endswith("end"):
                break
    finally:
        proc.wait()
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, args)

# ==========================
# MASTER
# ==========================

def write_master(base_dir: Path, rendus: List[Tuple[str, str, int]]):
    master_path = base_dir / "master.m3u8"
    with master_path.open("w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for res_name, res_str, bitrate in rendus:
            f.write(f"#EXT-X-STREAM-INF:BANDWIDTH={bitrate*1000},RESOLUTION={res_str}\n")
            f.write(f"{res_name}/{res_name}.m3u8\n")
    log_ok(t("master_done", path=master_path))

# ==========================
# RENDER (UI)
# ==========================

def build_files_table(file_states: List[Dict]) -> Table:
    table = Table(title=t("files_title"), box=box.SIMPLE_HEAVY)
    table.add_column(t("col_num"), justify="right", style="bold")
    table.add_column(t("col_file"), overflow="fold")
    table.add_column(t("col_dur"))
    table.add_column(t("col_langs"))
    table.add_column(t("col_status"), justify="center")
    for st in file_states:
        dur = f"{st['duration']:.1f}s" if st["duration"] else "-"
        langs = ", ".join(st["langs"]) if st["langs"] else "–"
        table.add_row(
            str(st["idx"]),
            st["name"],
            dur,
            langs,
            st["status"],
        )
    return table

def build_layout(files_table: Table, progress: Progress) -> Group:
    return Group(
        Panel(files_table, title="Files", border_style="title"),
        Panel(progress, title="Progress", border_style="title"),
    )

# ==========================
# MAIN PIPELINE
# ==========================

def convert_one_file(src: Path, out_root: Path, progress: Progress, file_states: List[Dict], state_idx: int, mode: str):
    info = ffprobe_json(src)
    fps, duration = get_video_fps_and_duration(info)

    audio_map = get_ordered_audio_map(info)
    audio_langs_ordered = [lang for (_pos, lang) in audio_map]

    gop = max(1, int(round(fps * GOP_SECONDS)))

    file_states[state_idx]["duration"] = duration
    file_states[state_idx]["langs"] = audio_langs_ordered
    file_states[state_idx]["status"] = t("pending")

    base_name = src.stem
    work_dir = out_root / base_name
    work_dir.mkdir(exist_ok=True)
    for r, _, _, _ in RESOLUTIONS:
        (work_dir / r).mkdir(exist_ok=True)

    # Checks GPU
    nvenc = detect_nvenc_available()
    cuda_scale = detect_scale_cuda_available()
    if not nvenc:
        raise RuntimeError(t("nvenc_missing"))
    if cuda_scale:
        log_info(t("cuda_filters_on"))
    else:
        if SOFT_SCALE_IF_NEEDED:
            log_warn(t("cuda_filters_off"))
        else:
            raise RuntimeError(t("cuda_filters_required"))

    # Task globale
    total_for_all_res = duration * len(RESOLUTIONS)
    task_overall = progress.add_task(f"[white]{t('file_task')}[/] {base_name}", total=total_for_all_res)

    ok_rendus: List[Tuple[str, str, int]] = []  # (res_name, res_master, bitrate)

    # Encode par résolution
    for res_name, scale_str, res_master, v_kbps in RESOLUTIONS:
        playlist_out = work_dir / res_name / f"{res_name}.m3u8"
        segments_out = work_dir / res_name / "%03d.ts"  # remplacé en .m4s si mode=fmp4

        args = build_ffmpeg_cmd(
            src=src,
            out_playlist=playlist_out,
            out_segments_pattern=segments_out,
            scale_str=scale_str,
            v_bitrate_k=v_kbps,
            gop=gop,
            audio_map=audio_map,
            use_cuda_scale=cuda_scale,
            mode=mode,
        )

        task_res = progress.add_task(f"[white]{res_name}", total=duration)
        try:
            # 1) tentative CUDA/NPP
            run_ffmpeg_with_progress(args, total_seconds=duration, task_id=task_res, progress=progress, cwd=playlist_out.parent)
        except subprocess.CalledProcessError as e1:
            # 2) fallback CPU si autorisé
            if SOFT_SCALE_IF_NEEDED:
                log_warn(t("fallback_cpu", name=base_name, res=res_name))
                args_fb = build_ffmpeg_cmd(
                    src=src,
                    out_playlist=playlist_out,
                    out_segments_pattern=segments_out,
                    scale_str=scale_str,
                    v_bitrate_k=v_kbps,
                    gop=gop,
                    audio_map=audio_map,
                    use_cuda_scale=False,
                    mode=mode,
                )
                try:
                    run_ffmpeg_with_progress(args_fb, total_seconds=duration, task_id=task_res, progress=progress, cwd=playlist_out.parent)
                except subprocess.CalledProcessError as e2:
                    log_err(f"{base_name} [{res_name}]: {e2}")
                    file_states[state_idx]["status"] = f"{t('error')} ({res_name})"
                    progress.stop_task(task_res)
                    continue
            else:
                log_err(f"{base_name} [{res_name}]: {e1}")
                file_states[state_idx]["status"] = f"{t('error')} ({res_name})"
                progress.stop_task(task_res)
                continue

        # Résolution OK
        progress.update(task_overall, advance=duration)
        progress.stop_task(task_res)
        log_ok(t("ok_variant", name=base_name, res=res_name))

        prev = file_states[state_idx]["status"]
        file_states[state_idx]["status"] = f"OK ({res_name})" if prev == t("pending") else f"{prev}, {res_name}"
        ok_rendus.append((res_name, res_master, v_kbps))

    # Master (uniquement les résolutions qui ont réussi)
    if ok_rendus:
        write_master(work_dir, [(rn, rstr, br) for (rn, rstr, br) in ok_rendus])
    else:
        file_states[state_idx]["status"] = t("error")

    if DELETE_SOURCE:
        try:
            src.unlink()
            log_warn(f"Source supprimée : {src}")
        except Exception as e:
            log_warn(f"Impossible de supprimer la source : {e}")

    progress.stop_task(task_overall)
    if t("error") not in file_states[state_idx]["status"]:
        file_states[state_idx]["status"] = "done"

def ask_mode_interactive() -> str:
    while True:
        ans = input(t("ask_mode")).strip()
        if ans == "1":
            return "ts"
        if ans == "2":
            return "fmp4"
        print(t("ask_mode_invalid"))

def main():
    mode = ask_mode_interactive()

    scan = Path(INPUT_DIR).resolve()
    out_root = Path(OUTPUT_DIR).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    # Récursif + tri pour un ordre stable
    mkvs = sorted(p for p in scan.rglob("*.mkv") if p.is_file())
    if not mkvs:
        console.print(Panel(t("no_mkv"), title=t("app_title"), style="warn"))
        return

    file_states: List[Dict] = [{
        "idx": i+1,
        "name": f.stem,
        "duration": 0.0,
        "langs": [],
        "status": t("scanning"),
        "path": f,
    } for i, f in enumerate(mkvs)]

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        expand=True,
    )

    progress.start()
    with Live(refresh_per_second=10, auto_refresh=False, console=console) as live:
        files_table = build_files_table(file_states)
        live.update(Panel(build_layout(files_table, progress), title=t("app_title"), border_style="title"))
        live.refresh()

        for i, f in enumerate(mkvs):
            try:
                convert_one_file(f, out_root, progress, file_states, i, mode)
            except Exception as e:
                log_err(f"{f.name}: {e}")
            files_table = build_files_table(file_states)
            live.update(Panel(build_layout(files_table, progress), title=t("app_title"), border_style="title"))
            live.refresh()
    progress.stop()

    mode_name = t("mode_name_fmp4") if mode == "fmp4" else t("mode_name_ts")
    console.print(Panel(f"{t('done')}  ({mode_name})", title=t("app_title"), style="ok"))

if __name__ == "__main__":
    main()
