# Estudio Preliminar para Sistema de Detección Inteligente EPP

[![Licencia: CC BY-NC-ND 4.0](https://img.shields.io/badge/Licencia-CC_BY--NC--ND_4.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-nd/4.0/deed.es)

![Base YOLO26](https://img.shields.io/badge/Base_Model-YOLO26-FF6B35?style=flat&logo=YOLO&logoColor=white&colorA=003366&colorB=FF6B35)
![EPP Model v1.0](https://img.shields.io/badge/EPP_Model-v1.0-003366?style=flat&logo=pytorch&logoColor=white&colorA=003366&colorB=EE4C2C)            

Este repositorio contiene el código fuente y la documentación del proyecto de residencia profesional "Estudio Preliminar para Sistema de Detección Inteligente EPP mediante el uso de IA en Laboratorios". El objetivo es desarrollar y evaluar la viabilidad de un sistema de visión por computadora para la detección en tiempo real del uso correcto de Equipos de Protección Personal (EPP) en laboratorios de industrias alimentarias.

## Descripción del Proyecto
El sistema está compuesto por tres servicios principales orquestados con Docker Compose:

* **Backend (Flask API):** Contiene los modelos de IA (`yolo26m.pt` para personas y `modeloepp_v1.pt` para EPP) y expone múltiples endpoints: `/api/detect` para inferencia, un panel de control web interactivo (HTML/JS) en la raíz, y un CRUD completo para gestionar la base de datos MariaDB.
* **Base de datos (MariaDB):** Almacena todas las detecciones, sesiones, alertas y métricas de entrenamiento. Se inicializa automáticamente con el esquema proporcionado.
* **Frontend Streamlit (opcional):** Interfaz alternativa de captura en tiempo real, pensada para la fase de recolección de datos durante la residencia. No es necesaria para el funcionamiento del sistema principal.

La aplicación web principal (`http://localhost:5000`) permite:

* Visualizar el video de la cámara en tiempo real con detecciones superpuestas.
* Subir imágenes para análisis.
* Consultar el historial de detecciones con filtros.
* Ver gráficos de métricas de entrenamiento.
* Administrar la configuración de los modelos.

## Tecnologías Principales
* Python 3.11
* Ultralytics YOLO (v26)
* Flask (backend y API)
* MariaDB (base de datos)
* HTML5 / JavaScript / Chart.js (frontend web)
* Streamlit (interfaz opcional de captura)
* Docker & Docker Compose
* OpenCV

## Estructura del Proyecto

```
.
├── app/
│   ├── backend/                    # Backend Flask + web
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app.py                  # Aplicación principal
│   │   ├── models/                  # Modelos YOLO (yolo26m.pt, modeloepp_v1.pt)
│   │   ├── templates/                # Plantillas HTML
│   │   │   ├── index.html
│   │   │   └── database.html
│   │   ├── static/                    # Archivos estáticos (CSS, JS)
│   │   │   ├── css/
│   │   │   │   ├── style.css
│   │   │   │   └── database.css
│   │   │   └── js/
│   │   │       ├── utils.js
│   │   │       ├── dashboard.js
│   │   │       └── crud.js
│   │   └── ... (otros archivos)
│   ├── frontend/                   # (Opcional) Interfaz Streamlit
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── dashboard_captura.py
│   └── db/                          # Scripts de inicialización de la base de datos
│       └── init/
│           └── setup_db.sql
├── data/                            # Datasets e imágenes (ignorado por git)
├── notebooks/                        # Notebooks de Jupyter
├── .devcontainer/                    # Configuración de desarrollo en contenedor
│   └── devcontainer.json
├── .gitignore
├── docker-compose.yml                # Orquestador de servicios
├── LICENSE
└── README.md
```

## Cómo Empezar (Configuración para Desarrolladores)

### Prerrequisitos

* Docker y Docker Compose instalados en tu sistema.
* (Opcional) Visual Studio Code con las extensiones recomendadas (ver más abajo) si deseas usar el devcontainer.

### Pasos para ejecutar el proyecto

1.  **Clona el repositorio:**
    ```bash
    git clone <url_de_tu_repositorio>
    cd deteccioneppalimentarias
    ```

2. **Prepara los modelos YOLO**
   
   Coloca los archivos `yolo26m.pt` y `modeloepp_v1.pt` en `app/backend/models/`. Si no los tienes, puedes descargarlos o entrenarlos según la documentación de Ultralytics.

3. **Construye y levanta los servicios con Docker Compose:**
    ```bash
    docker-compose up --build
    ```
    Esto iniciará:
    * La base de datos MariaDB en `localhost:3307`
    * El backend Flask en `http://localhost:5000`
    * (Opcional) El frontend Streamlit en `http://localhost:8501`

4. **Accede a la aplicación:**
   * **Panel principal:** `http://localhost:5000`
   * **Gestión de base de datos:** `http://localhost:5000/database`
   * **API de detección:** `POST` `http://localhost:5000/api/detect` (enviando una * imagen con el campo `image`)
    * **Streamlit (si está habilitado):** `http://localhost:8501`

5. **Detener los servicios:**
    ```bash
    docker-compose down
    ```
    Si deseas eliminar también los volúmenes de la base de datos (borrar todos los datos), añade `-v`.

## Variables de entorno

Las variables de entorno se encuentran en el archivo `.env` en la raiz del proyecto. Las variables disponibles son:
* `MARIADB_ROOT_PASSWORD`
* `MARIADB_USER`
* `MARIADB_PASSWORD`
* `FLASK_ENV`
    * Dentro del archivo `.env` deben de definirse las credenciales a usar.

## Extensiones de VSCode Recomendadas

Para un desarrollo más cómodo, se recomienda instalar:
* **Dev Containers** (`ms-vscode-remote.remote-containers`) – para trabajar dentro del contenedor.
* **Python** (`ms-python.python`) y Pylance.
* **Docker** (`ms-azuretools.vscode-docker`).
* **GitLens** (`eamodio.gitlens`) – para visualizar el historial.
* **Thunder Client** (`rangav.vscode-thunder-client`) – para probar la API.

## Licencia

Este proyecto está licenciado bajo la licencia **Creative Commons Atribución-NoComercial-SinDerivadas 4.0 Internacional (CC BY-NC-ND 4.0)**. Esto significa que puedes compartirlo, pero no modificarlo ni usarlo con fines comerciales sin el permiso explícito del autor.

El texto completo de la licencia está disponible en el archivo `LICENSE` de este repositorio y en [https://creativecommons.org/licenses/by-nc-nd/4.0/deed.es](https://creativecommons.org/licenses/by-nc-nd/4.0/deed.es).