"""Build an explicit static portfolio viewer. No API key or live generation is shipped."""

import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root / "work/public-site"
(out / "static").mkdir(parents=True, exist_ok=True)
for file in (root / "app/static").iterdir():
    shutil.copyfile(
        file, out / ("index.html" if file.name == "index.html" else "static/" + file.name)
    )
shutil.copyfile(root / "evals/sample-report.json", out / "sample.json")
shutil.copyfile(root / "evals/sample-report.md", out / "sample.md")
(out / "config.json").write_text(
    json.dumps(
        {
            "provider": "saved_sample",
            "source": "pinned_fixture",
            "public_sample_only": True,
            "generation_configured": False,
        }
    )
)
(out / "vercel.json").write_text(
    json.dumps(
        {
            "version": 2,
            "rewrites": [
                {"source": "/config", "destination": "/config.json"},
                {"source": "/sample", "destination": "/sample.json"},
            ],
            "headers": [
                {
                    "source": "/(.*)",
                    "headers": [
                        {"key": "X-Content-Type-Options", "value": "nosniff"},
                        {
                            "key": "Content-Security-Policy",
                            "value": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
                        },
                    ],
                }
            ],
        }
    )
)
print(out)
