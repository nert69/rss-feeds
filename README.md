# RSS feeds

RSS feeds for sites that do not publish their own. GitHub Actions regenerates
the feeds every hour, validates the XML, and commits only genuine changes.

## Available feed

| Site | Subscribe |
| --- | --- |
| [Habbo Hotel: Origins community news](https://origins.habbo.com/community/category/all/1) | [habbo-origins-community.rss](https://raw.githubusercontent.com/nert69/rss-feeds/main/habbo-origins-community.rss) |
| [Macklebee on X (@SulakeDominic)](https://x.com/SulakeDominic) | [sulake-dominic.rss](https://raw.githubusercontent.com/nert69/rss-feeds/main/sulake-dominic.rss) |

The feed stays at its original URL so existing RSS reader subscriptions keep
working.

## How it works

1. `feeds.yaml` lists every generator and its output file.
2. `feed_generators/run_all_feeds.py` runs the enabled generators.
3. `feed_generators/validate_feeds.py` rejects empty or malformed feeds.
4. `.github/workflows/update-feeds.yml` runs the process hourly and publishes
   changed XML with GitHub's short-lived Actions token.

No personal GitHub token is stored in this repository.

## Run locally

Python 3.11 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
python feed_generators\run_all_feeds.py
python feed_generators\validate_feeds.py
```

## Add another feed

Create a generator in `feed_generators/`, make it write RSS 2.0 XML, then add
its script and output path to `feeds.yaml`. The runner and validator will pick
it up automatically.
