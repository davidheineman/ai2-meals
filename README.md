### setup

```sh
uv sync
```

### usage

```sh
python ingest_meals.py
```

```sh
# vis
python analysis/extract_mains.py -o csv/mains.csv
python analysis/visualize_mains.py -o plot/mains-heatmap.png
```