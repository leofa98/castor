from pathlib import Path

from platformdirs import user_data_dir

data_dir = Path(user_data_dir("castor", appauthor=False))
print(data_dir)
data_dir.mkdir(parents=True, exist_ok=True)
print("creado")
