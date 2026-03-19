find . -name "*.py" -exec sh -c 'uconv -x "Fullwidth-Halfwidth" "$1" > "$1.tmp" && mv "$1.tmp" "$1"' _ {} \;
