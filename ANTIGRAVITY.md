# Instrucciones Personalizadas para GitHub Copilot

## Estilo de Código

- Utiliza nombres descriptivos y significativos para variables, funciones y clases
- Sigue las convenciones de nomenclatura del lenguaje correspondiente
- Mantén las funciones pequeñas y enfocadas en una única responsabilidad
- Prioriza la legibilidad sobre la concisión excesiva
- Maximiza la simplicidad del código

## Documentación

- Documenta funciones y clases con comentarios claros
- Incluye ejemplos de uso cuando sea apropiado
- Explica el "por qué" en los comentarios, no solo el "qué"
- Mantén la documentación actualizada con los cambios de código
- EL directorio para TODA la docuentación es /docs

## Mejores Prácticas

- Escribe código modular y reutilizable
- Aplica principios SOLID cuando sea relevante
- Maneja errores de manera apropiada y consistente
- Evita la duplicación de código (DRY - Don't Repeat Yourself)
- Considera la seguridad en todas las implementaciones

## Testing

- Escribe tests para funcionalidades nuevas y cambios importantes
- Sigue patrones de testing establecidos en el proyecto
- Prioriza tests que aporten valor y cobertura significativa

## Seguridad

- Valida y sanitiza todas las entradas de usuario
- No incluyas credenciales, claves API o información sensible en el código
- Utiliza variables de entorno para configuración sensible
- Implementa autenticación y autorización adecuadas

## Performance

- Considera la eficiencia en operaciones con grandes volúmenes de datos
- Optimiza consultas a bases de datos
- Evita operaciones costosas innecesarias en bucles

## Comentarios de Código

- Prefiere código autoexplicativo sobre comentarios excesivos
- Usa comentarios para explicar lógica compleja o decisiones no obvias
- Mantén los comentarios concisos y relevantes

## Control de Versiones

- Escribe mensajes de commit descriptivos y claros
- Agrupa cambios relacionados en commits lógicos
- Mantén los commits atómicos y enfocados

## Entorno de Desarrollo

- Usar **pyenv** para gestionar versiones de Python
- Usar **pyenv-virtualenv** para entornos virtuales
- Python 3.11+ requerido
- Archivo `.python-version` en la raíz define la versión del proyecto



### Convenciones de Nombres

- Archivos Python: snake_case (ej: `example_scraper.py`)
- Clases: PascalCase (ej: `BrowserManager`, `ExampleScraper`)
- Funciones y métodos: snake_case (ej: `get_page`, `scrape_data`)
- Constantes: UPPER_SNAKE_CASE (ej: `DEFAULT_WAIT`)
- Variables de entorno: UPPER_SNAKE_CASE (ej: `HEADLESS`, `LOG_LEVEL`)

### versionado

- Cada vez que se realice un cambio en el codigo que implica no preservar la compatibilidad con versiones anteriores, se debe actualizar el número de versión en el archivo 'pyproject.toml' siguiendo el formato `MAJOR.MINOR.PATCH` (ej: `1.0.0` → `2.0.0`). En cconcreto se debe actualizar el número de versión mayor (MAJOR) para indicar que se han introducido cambios incompatibles con versiones anteriores.
- Cada vez que se realice un cambio en el código que preserve la compatibilidad con versiones anteriores pero añada nuevas funcionalidades, se debe actualizar el número de versión en el archivo 'pyproject.toml' siguiendo el formato `MAJOR.MINOR.PATCH` (ej: `1.0.0` → `1.1.0`). En concreto se debe actualizar el número de versión menor (MINOR) para indicar que se han añadido nuevas funcionalidades sin romper la compatibilidad con versiones anteriores.
- Cada vez que se realice un cambio en el código que preserve la compatibilidad con versiones anteriores pero corrija errores o realice mejoras menores, se debe actualizar el número de versión en el archivo 'pyproject.toml' siguiendo el formato `MAJOR.MINOR.PATCH` (ej: `1.0.0` → `1.0.1`). En concreto se debe actualizar el número de versión de parche (PATCH) para indicar que se han corregido errores o realizado mejoras menores sin romper la compatibilidad con versiones anteriores.
