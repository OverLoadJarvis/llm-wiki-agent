import sys
import argparse
from tqdm import tqdm
from pathlib import Path
from markitdown import MarkItDown

CONVERTIBLE_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls",
    ".html", ".htm", ".txt", ".csv", ".json", ".xml",
    ".rst", ".rtf", ".epub", ".ipynb",
    ".yaml", ".yml", ".tsv",
    ".wav", ".mp3",
}
ALL_EXTENSIONS = {".md"} | CONVERTIBLE_EXTENSIONS


def convert_directory_to_md(input_dir: Path, delete_source: bool = False):
    md = MarkItDown(enable_plugins=False)

    files_to_process = [f for f in input_dir.rglob('*') if f.is_file()]

    if not files_to_process:
        print(f"No files found in {input_dir}!")
        return

    for file_path in tqdm(files_to_process, desc="Converting Files"):
        if file_path.name.startswith('.'):
            continue

        if file_path.suffix.lower() == '.md':
            tqdm.write(f"Skipping (already .md): {file_path.name}")
            continue

        output_path = file_path.with_suffix(".md")
        try:
            result = md.convert(str(file_path))
            output_path.write_text(result.text_content, encoding="utf-8")
            if delete_source:
                file_path.unlink()
            tqdm.write(f"Converted: {file_path.name}")
        except Exception as e:
            tqdm.write(f"FAILED: Could not convert '{file_path.name}'. Reason: {e}")


def import_dir_to_db(project_name: str, input_dir: str, delete_source: bool = False):
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from storage.db import WikiStorage

    input_path = Path(input_dir).resolve()
    if not input_path.is_dir():
        print(f"Error: directory not found: {input_dir}")
        return

    db = WikiStorage("storage/wiki.db")
    proj = db.get_project_by_name(project_name)
    if not proj:
        print(f"Error: project '{project_name}' not found.")
        db.close()
        return

    pid = proj["id"]
    print(f"[DB] Project: {project_name} (id={pid})")
    print(f"[DB] Input dir: {input_path}")

    files_to_process = [
        f for f in input_path.rglob('*')
        if f.is_file()
        and not f.name.startswith('.')
        and f.suffix.lower() in ALL_EXTENSIONS
    ]

    if not files_to_process:
        print("No supported files found in directory.")
        db.close()
        return

    md_converter = MarkItDown(enable_plugins=False)

    for file_path in tqdm(files_to_process, desc="Importing to DB"):
        rel_name = file_path.relative_to(input_path).as_posix()
        md_rel_path = f"raw/{Path(rel_name).with_suffix('.md')}"

        existing = db.get_file_by_path(pid, md_rel_path)
        if existing:
            tqdm.write(f"Skipping (exists in DB): {md_rel_path}")
            continue

        if file_path.suffix.lower() == '.md':
            content = file_path.read_text(encoding="utf-8")
        else:
            try:
                result = md_converter.convert(str(file_path))
                content = result.text_content
            except Exception as e:
                tqdm.write(f"FAILED: Could not convert '{file_path.name}'. Reason: {e}")
                continue

        db.add_file(pid, md_rel_path, content)
        if delete_source:
            file_path.unlink()
        tqdm.write(f"Imported: {file_path.name} -> {md_rel_path}")

    db.close()
    print(f"\nDone. {len(files_to_process)} files processed.")


def main(args):
    if args.project:
        if not args.input_dir:
            print("Error: --input_dir is required with --project")
            return
        import_dir_to_db(args.project, args.input_dir, args.delete_source)
        return

    input_path = Path(args.input_dir).resolve()
    print("-" * 40)
    print(f"Input Directory: {input_path}")
    print("-" * 40)

    try:
        convert_directory_to_md(input_path, args.delete_source)
        print("\nConversion process complete.")
    except FileNotFoundError:
        print(f"\nError: Input directory not found at {input_path}")
    except Exception as e:
        print(f"\nAn unexpected error occurred during execution: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert files in a directory to Markdown. "
                    "Local mode: convert in-place. DB mode: import into project."
    )
    parser.add_argument(
        "--input_dir",
        type=str,
        help="Input directory path."
    )
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Project name in DB: convert files from input_dir and store as raw/*.md"
    )
    parser.add_argument(
        "--delete_source",
        action="store_true",
        help="Delete original source files after conversion."
    )
    args = parser.parse_args()
    main(args)
