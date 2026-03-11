```bash
bash scripts/upload-doc-images-to-r2.sh \
    --remote astrbot-docs-s3 \
    --bucket astrbot \
    --prefix docs \
    --rewrite-markdown \
    --public-base-url https://files.astrbot.app
```