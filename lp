#!/usr/bin/env python3
import html
import os
import subprocess
import sys
import tempfile
from pathlib import Path

LP_BIN = "/usr/bin/lp"
TEXT_EXTS = {".txt", ".log", ".md"}
OFFICE_EXTS = {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp"}


def find_print_file(args):
    file_args = []
    for arg in args:
        p = Path(arg)
        if p.is_file():
            file_args.append(p)
    if len(file_args) != 1:
        return None
    return file_args[0]


def text_to_pdf(src: Path) -> Path:
    text = src.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    escaped = html.escape(text)
    html_doc = f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      background: #ffffff;
    }}
    body {{
      font-family: \"Noto Sans CJK SC\", \"Noto Sans CJK\", \"WenQuanYi Zen Hei\", sans-serif;
      color: #000000;
      font-size: 17pt;
      line-height: 1.6;
      font-weight: 500;
      padding: 10mm 12mm 12mm 12mm;
      box-sizing: border-box;
    }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font: inherit;
    }}
  </style>
</head>
<body>
  <pre>{escaped}</pre>
</body>
</html>
"""
    out_dir = Path(tempfile.mkdtemp(prefix="lp-text-"))
    html_path = out_dir / f"{src.stem}.html"
    out_pdf = out_dir / f"{src.stem}.pdf"
    html_path.write_text(html_doc, encoding="utf-8")
    cmd = [
        "wkhtmltopdf",
        "--encoding",
        "utf-8",
        "--page-size",
        "A4",
        "--margin-top",
        "8",
        "--margin-right",
        "8",
        "--margin-bottom",
        "10",
        "--margin-left",
        "8",
        str(html_path),
        str(out_pdf),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(f"wkhtmltopdf convert failed: {stderr}")
    if not out_pdf.exists():
        raise RuntimeError(f"wkhtmltopdf did not produce PDF for {src}")
    return out_pdf


def office_to_pdf(src: Path) -> Path:
    out_dir = Path(tempfile.mkdtemp(prefix="lp-office-"))
    profile_dir = Path(tempfile.mkdtemp(prefix="lo-profile-"))
    cmd = [
        "soffice",
        f"-env:UserInstallation=file://{profile_dir}",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(out_dir),
        str(src),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(f"LibreOffice convert failed: {stderr}")
    out_pdf = out_dir / f"{src.stem}.pdf"
    if not out_pdf.exists():
        raise RuntimeError(f"LibreOffice did not produce PDF for {src}")
    return out_pdf


def main():
    args = sys.argv[1:]
    print_file = find_print_file(args)
    if print_file is None:
        os.execv(LP_BIN, [LP_BIN, *args])

    ext = print_file.suffix.lower()
    if ext in TEXT_EXTS:
        pdf_path = text_to_pdf(print_file)
    elif ext in OFFICE_EXTS:
        pdf_path = office_to_pdf(print_file)
    else:
        os.execv(LP_BIN, [LP_BIN, *args])

    mapped_args = [str(pdf_path) if Path(arg) == print_file else arg for arg in args]
    print(f"[safe-lp] auto-converted {print_file} -> {pdf_path}", file=sys.stderr)
    os.execv(LP_BIN, [LP_BIN, *mapped_args])


if __name__ == "__main__":
    main()