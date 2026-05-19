echo "全角转半角脚本，依赖uconv工具"
echo "Ctrl + C 结束"
find . -name "*.py" -exec sh -c 'uconv -x "Fullwidth-Halfwidth" "$1" > "$1.tmp" && mv "$1.tmp" "$1"' _ {} \;
