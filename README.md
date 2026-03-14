# Estudio Preliminar para Sistema de Detección Inteligente EPP

[![Licencia: CC BY-NC-ND 4.0](https://img.shields.io/badge/Licencia-CC_BY--NC--ND_4.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-nd/4.0/deed.es)

Este repositorio contiene el código fuente y la documentación del proyecto de residencia profesional "Estudio Preliminar para Sistema de Detección Inteligente EPP mediante el uso de IA en Laboratorios". El objetivo es desarrollar y evaluar la viabilidad de un sistema de visión por computadora para la detección en tiempo real del uso correcto de Equipos de Protección Personal (EPP) en laboratorios de industrias alimentarias.

## Descripción del Proyecto

El sistema se compone de dos partes principales:

*   **Backend (Flask API):** Contiene los modelos de IA (`yolo26m.pt` para personas y `model_epp_v26.pt` para EPP) y expone un endpoint `/detect` para realizar la inferencia.
*   **Frontend (Streamlit):** Proporciona una interfaz de usuario para conectarse a una cámara, visualizar el video en tiempo real con las detecciones superpuestas y capturar imágenes para aumentar el dataset.

## Tecnologías Principales

*   Python 3.11
*   Ultralytics YOLO (v26)
*   Flask
*   Streamlit
*   Docker & Docker Compose
*   OpenCV

## Estructura del Proyecto

```
.
├── app/
│   ├── backend/          # Código de la API Flask
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── app.py
│   └── frontend/         # Código de la interfaz Streamlit
│       ├── Dockerfile
│       ├── requirements.txt
│       └── dashboard_captura.py
├── data/                 # Datasets e imágenes (ignorado por git)
├── models/               # Modelos entrenados (ignorado por git, excepto los `.pt` finales)
│   ├── yolo26m.pt
│   └── final/
│       └── epp_production/
│           └── model_epp_v26.pt
├── notebooks/            # Notebooks de Jupyter para análisis y entrenamiento
├── .devcontainer/        # Configuración del entorno de desarrollo en contenedor
│   └── devcontainer.json
├── .gitignore
├── docker-compose.yml    # Orquestador de servicios (backend y frontend)
├── LICENSE
└── README.md
```

## Cómo Empezar (Configuración para Desarrolladores)

### Prerrequisitos

*   Docker y Docker Compose instalados en tu sistema.
*   Visual Studio Code con las extensiones recomendadas (ver más abajo).

### Pasos para ejecutar el proyecto

1.  **Clona el repositorio:**
    ```bash
    git clone <url_de_tu_repositorio>
    cd deteccioneppalimentarias
    ```
2.  **Abre el proyecto en VSCode.**
3.  **Vuelve a abrir en el contenedor:** Cuando VSCode detecte la carpeta `.devcontainer`, te preguntará si quieres "Reabrir en el contenedor". Acepta. Esto construirá el entorno de desarrollo unificado.
4.  **Construye y levanta los servicios:**
    Desde una terminal dentro del contenedor (o en tu máquina, con Docker corriendo), ejecuta en la raíz del proyecto:
    ```bash
    docker-compose up --build
    ```
5.  **Accede a la aplicación:**
    *   **Frontend (Interfaz de usuario):** `http://localhost:8501`
    *   **Backend (API):** `http://localhost:5000` (el endpoint de detección es `POST /detect`)

### Extensiones de VSCode Recomendadas

Para una experiencia de desarrollo óptima, se recomienda instalar las extensiones listadas en el archivo `.devcontainer/devcontainer.json` (Python, Jupyter) y añadir manualmente Docker, GitLens, Thunder Client, etc., para un flujo de trabajo más completo.

## Licencia

Este proyecto está licenciado bajo la licencia **Creative Commons Atribución-NoComercial-SinDerivadas 4.0 Internacional (CC BY-NC-ND 4.0)**. Esto significa que puedes compartirlo, pero no modificarlo ni usarlo con fines comerciales sin el permiso explícito del autor.

El texto completo de la licencia está disponible en el archivo `LICENSE` de este repositorio y en [https://creativecommons.org/licenses/by-nc-nd/4.0/deed.es](https://creativecommons.org/licenses/by-nc-nd/4.0/deed.es).