[Read in English](README.md)

# Castor

Un cliente de podcasts para la terminal. Es un proyecto/experimento hecho con la finalidad de practicar Python.

Permite buscar podcasts, suscribirse, ver sus episodios y descargarlos. Tiene una versión de línea de comandos y otra con interfaz de texto (hecha con [Textual](https://textual.textualize.io/)). Ambas usan el mismo código por debajo.

No reproduce audio. Al pulsar `p` sobre un episodio descargado, se abre con el reproductor que el sistema tenga por defecto.

## Cómo probarlo

```
pip install requests feedparser rich platformdirs textual pytest
```



Con la interfaz de texto (Recomendado):

```
python tui.py
```

Con la línea de comandos:

```
python project.py search "lex fridman"
python project.py subscribe <url_del_feed>
python project.py list
python project.py episodes "<título del podcast>"
python project.py download <id_del_episodio>
python project.py refresh
```

Teclas: `s` buscar, `r` refrescar, `d` descargar, `p` reproducir, `q` salir, `esc` volver.

## Cómo funciona (por encima)

- Busca podcasts con la API de iTunes y lee los episodios del feed RSS con `feedparser`.
- Guarda todo en un único `library.json` en la carpeta de datos del usuario, así que al cerrar y volver a abrir sigue todo ahí.
- Escribe el fichero de forma segura y, si se corrompe, hace una copia de seguridad y empieza de cero.
- Detecta episodios nuevos por el `guid` del RSS, no por el título.

## Ficheros

- `project.py`: la CLI y las funciones principales
- `tui.py`: la interfaz con Textual
- `library.py`: lee y guarda `library.json`
- `models.py`: las clases `Podcast` y `Episode`
- `exceptions.py`: los errores propios
- `test_project.py`: los tests (no necesitan internet)

## Tests

```
pytest test_project.py -v
```