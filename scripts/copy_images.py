import os
import sys
import shutil
from pathlib import Path

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def clear_folder(p: Path):
    for child in p.iterdir():
        # don't remove .gitkeep if present, but remove images and other files
        if child.is_file():
            try:
                child.unlink()
            except Exception as e:
                print(f"Warning: could not remove {child}: {e}")


def copy_images(dest_dir: Path, src_paths):
    ensure_dir(dest_dir)
    # clear existing files
    clear_folder(dest_dir)

    copied = []
    for i, sp in enumerate(src_paths, start=1):
        src = Path(sp)
        if not src.exists():
            print(f"Source not found: {src}")
            continue
        # normalize destination filename
        suffix = src.suffix or '.png'
        dest_name = f"screenshot_{i}{suffix}"
        dest = dest_dir / dest_name
        try:
            shutil.copy2(src, dest)
            copied.append(dest.name)
            print(f"Copied: {src} -> {dest}")
        except Exception as e:
            print(f"Failed to copy {src} -> {dest}: {e}")
    return copied

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python copy_images.py <path-to-image1> [<path-to-image2> ...]")
        sys.exit(1)

    dest = Path(__file__).parent.parent / 'web' / 'assets' / 'images'
    srcs = sys.argv[1:]
    log_file = Path(__file__).parent / 'copy_images.log'
    def log(msg):
        try:
            with log_file.open('a', encoding='utf-8') as f:
                f.write(msg + "\n")
        except Exception:
            pass
    log(f"Starting copy_images.py; destination: {dest}")
    print(f"Destination folder: {dest}")
    copied = copy_images(dest, srcs)
    if copied:
        print("Done. Copied files:")
        for n in copied:
            print(" - ", n)
            log(f"COPIED: {n}")
    else:
        print("No files copied. Check source paths.")
        log("No files copied. Check source paths or permissions.")
    log("Finished copy_images.py")
