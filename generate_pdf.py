import os
import sys
import subprocess
import markdown

base_dir = r"D:\Project\Multi Agent Trading Bot"
md_path = os.path.join(base_dir, "docs", "SYSTEM_DOCUMENTATION.md")
html_path = os.path.join(base_dir, "docs", "SYSTEM_DOCUMENTATION.html")
pdf_path = os.path.join(base_dir, "docs", "Delta_Exchange_MultiAgent_Trading_System_Documentation.pdf")
pdf_root_path = os.path.join(base_dir, "Delta_Exchange_MultiAgent_Trading_System_Documentation.pdf")

with open(md_path, "r", encoding="utf-8") as f:
    md_content = f.read()

# Convert markdown to html with table support
html_body = markdown.markdown(md_content, extensions=['tables', 'fenced_code', 'nl2br', 'toc'])

full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Delta Exchange Multi-Agent Trading System Documentation</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

  @page {{
    size: A4;
    margin: 18mm 16mm 18mm 16mm;
    @bottom-right {{
      content: counter(page);
    }}
  }}

  body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #1a202c;
    background-color: #ffffff;
    line-height: 1.65;
    font-size: 13.5px;
    margin: 0;
    padding: 0;
  }}

  /* Executive Cover Header */
  .cover-banner {{
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0369a1 100%);
    color: #ffffff;
    padding: 36px 32px;
    border-radius: 12px;
    margin-bottom: 28px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.12);
  }}

  .cover-banner h1 {{
    font-size: 26px;
    font-weight: 800;
    margin: 0 0 10px 0;
    color: #ffffff;
    letter-spacing: -0.5px;
    border-bottom: none;
    padding-bottom: 0;
  }}

  .cover-banner .subtitle {{
    font-size: 14px;
    color: #94a3b8;
    margin: 0 0 16px 0;
    font-weight: 400;
  }}

  .cover-banner .badges {{
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }}

  .badge {{
    display: inline-block;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    background: rgba(255, 255, 255, 0.15);
    color: #e2e8f0;
    border: 1px solid rgba(255, 255, 255, 0.2);
  }}

  .badge.primary {{
    background: #0284c7;
    color: #ffffff;
    border-color: #38bdf8;
  }}

  /* Typography */
  h1 {{
    font-size: 22px;
    font-weight: 700;
    color: #0f172a;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 8px;
    margin-top: 32px;
    margin-bottom: 16px;
    page-break-after: avoid;
  }}

  h2 {{
    font-size: 18px;
    font-weight: 700;
    color: #1e293b;
    border-bottom: 1.5px solid #f1f5f9;
    padding-bottom: 6px;
    margin-top: 26px;
    margin-bottom: 14px;
    page-break-after: avoid;
  }}

  h3 {{
    font-size: 15px;
    font-weight: 600;
    color: #0369a1;
    margin-top: 20px;
    margin-bottom: 10px;
    page-break-after: avoid;
  }}

  h4 {{
    font-size: 14px;
    font-weight: 600;
    color: #334155;
    margin-top: 16px;
    margin-bottom: 8px;
    page-break-after: avoid;
  }}

  p, ul, ol {{
    margin-top: 0;
    margin-bottom: 12px;
  }}

  li {{
    margin-bottom: 5px;
  }}

  blockquote {{
    margin: 16px 0;
    padding: 12px 18px;
    background-color: #f8fafc;
    border-left: 4px solid #0284c7;
    color: #334155;
    font-size: 13px;
    border-radius: 0 8px 8px 0;
  }}

  blockquote p {{
    margin: 0;
  }}

  /* Tables */
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 18px 0;
    font-size: 12.5px;
    page-break-inside: avoid;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    border-radius: 6px;
    overflow: hidden;
  }}

  th {{
    background-color: #0f172a;
    color: #ffffff;
    font-weight: 600;
    text-align: left;
    padding: 9px 12px;
    border: 1px solid #1e293b;
  }}

  td {{
    padding: 8px 12px;
    border: 1px solid #e2e8f0;
    vertical-align: top;
  }}

  tr:nth-child(even) {{
    background-color: #f8fafc;
  }}

  tr:hover {{
    background-color: #f1f5f9;
  }}

  /* Code blocks & Inline Code */
  code {{
    font-family: 'JetBrains Mono', Consolas, Monaco, monospace;
    font-size: 12px;
    background-color: #f1f5f9;
    color: #0f172a;
    padding: 2px 5px;
    border-radius: 4px;
    border: 1px solid #e2e8f0;
  }}

  pre {{
    background-color: #0f172a;
    color: #f8fafc;
    padding: 14px 16px;
    border-radius: 8px;
    overflow-x: auto;
    font-size: 11.5px;
    line-height: 1.5;
    margin: 16px 0;
    page-break-inside: avoid;
    border: 1px solid #1e293b;
  }}

  pre code {{
    background-color: transparent;
    color: inherit;
    padding: 0;
    border: none;
  }}

  /* Print optimizations */
  hr {{
    border: 0;
    height: 1px;
    background: #e2e8f0;
    margin: 24px 0;
  }}

  .page-break {{
    page-break-before: always;
  }}

  .footer-note {{
    text-align: center;
    font-size: 11px;
    color: #94a3b8;
    margin-top: 40px;
    border-top: 1px solid #e2e8f0;
    padding-top: 12px;
  }}
</style>
</head>
<body>

<div class="cover-banner">
  <h1>Delta Exchange Multi-Agent Trading System</h1>
  <div class="subtitle">Complete End-to-End Technical & Architectural Documentation</div>
  <div class="badges">
    <span class="badge primary">Version 2.5.0 Institutional</span>
    <span class="badge">10 Specialized Agents</span>
    <span class="badge">6 Hierarchical Layers</span>
    <span class="badge">Proprietary IVL Strategy</span>
    <span class="badge">Delta Exchange India</span>
  </div>
</div>

{html_body}

<div class="footer-note">
  Delta Exchange Multi-Agent Trading System &bull; Confidential & Proprietary Quantitative Architecture &bull; Generated Automatically
</div>

</body>
</html>
"""

with open(html_path, "w", encoding="utf-8") as f:
    f.write(full_html)

print(f"HTML successfully generated at: {html_path}")

# Run Chrome or Edge to compile to PDF
chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
browser_path = chrome_path if os.path.exists(chrome_path) else edge_path

cmd = [
    browser_path,
    "--headless",
    "--disable-gpu",
    "--no-pdf-header-footer",
    f"--print-to-pdf={pdf_path}",
    html_path
]

print(f"Compiling PDF with {os.path.basename(browser_path)}...")
res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode == 0 and os.path.exists(pdf_path):
    print(f"SUCCESS! PDF created at: {pdf_path} (Size: {os.path.getsize(pdf_path)} bytes)")
    import shutil
    shutil.copy2(pdf_path, pdf_root_path)
    print(f"Copied PDF to project root: {pdf_root_path}")
    # Also copy to artifact directory
    artifact_pdf = r"C:\Users\DELL\.gemini\antigravity\brain\84b64d4a-5947-4739-a58e-3523f1ee3dea\Delta_Exchange_MultiAgent_Trading_System_Documentation.pdf"
    shutil.copy2(pdf_path, artifact_pdf)
    print(f"Copied PDF to artifact directory: {artifact_pdf}")
else:
    print(f"Error compiling PDF: {res.stderr}")

