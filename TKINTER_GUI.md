# INTERFAZ TKINTER - DISEÑO DE ZAPATAS AISLADAS

## Estado de la Aplicación ✓

La interfaz Tkinter con visualizaciones 2D y 3D ha sido creada y probada exitosamente.

### Características Implementadas:

#### 1. **Datos de Entrada** (Pestaña 1)
- Entrada de propiedades del suelo (qa, gamma, Df)
- Entrada de geometría de la zapata (B, L, h, bx, by, recubrimiento)
- Entrada de materiales (f'c, fy, φ flexión, φ cortante)
- **Visualización 2D en tiempo real:** Vista superior de la zapata con:
  - Dimensiones B, L (ancho y largo)
  - Columna en el centro (rojo)
  - Zapata (azul)
  - Ejes X (verde) y Y (púrpura)
  - Espesor h (anotación)

#### 2. **Cargas** (Pestaña 2)
- Agregar casos de carga básicos (Muerta, Viva, Viento, etc.)
- Generar automáticamente combinaciones ACI/ASCE-7
- Agregar combinaciones manuales
- Importar combinaciones desde archivos Excel (.xlsx) o CSV (.csv)
- Tabla interactiva con todas las combinaciones
- **Visualización 3D:** Diagrama tridimensional que muestra:
  - La zapata (8 puntos conectados)
  - La columna sobre la zapata
  - Vectores de carga aplicada (N, Vx, Vy, Mx, My)
  - Colores diferenciados para cada tipo de fuerza

#### 3. **Análisis** (Pestaña 3)
- Parámetros de estabilidad configurables (μ, FS_deslizamiento, FS_volteo)
- Opción de permitir contacto parcial
- Ejecución de análisis completo:
  - Análisis de presiones de contacto
  - Verificación de estabilidad
  - Diseño estructural por flexión y cortante
  - Verificación por punzonamiento
- **Tablas de resultados:**
  - Presiones críticas (q_max, q_min, excentricidades)
  - Factores de seguridad (deslizamiento, volteo)
  - Diseño de acero (barras, espaciamiento)
- **Gráficos visuales:**
  - Presiones de contacto vs combinaciones (con límite qa)
  - Factores de seguridad por deslizamiento
  - Comparación visual de cumplimiento (verde OK / rojo FALLA)

#### 4. **Optimización** (Pestaña 4)
- Especificación de restricciones (B_min, B_max, L_min, L_max, h_min, h_max)
- Paso de búsqueda configurable
- Opción de zapata cuadrada (B=L)
- Objetivos de optimización: min_area, min_volume, min_cost, min_depth
- **Visualización 3D de la geometría óptima:**
  - Zapata óptima con todas sus dimensiones
  - Columna sobre la zapata
  - Anotaciones de B, L, h
  - Vista isométrica rotable

#### 5. **Resultados** (Pestaña 5)
- Resumen completo en formato JSON con todos los resultados
- Exportación a Excel (.xlsx) con tablas formateadas
- Exportación a PDF (.pdf) con gráficos
- Exportación a Word (.docx) con tablas y descripción


## Cómo Ejecutar la Aplicación

### Requisitos Previos:
```bash
# Asegúrate de que todas las dependencias estén instaladas
pip install -r requirements.txt
```

### Ejecutar la Interfaz:
```bash
# En PowerShell o CMD, navega a la carpeta del proyecto
cd "c:\Users\Kevin Flores\Documents\012-CALCULO-DE-ZAPATAS-AISLADAS"

# Ejecuta la aplicación Tkinter
python ui/tkinter_app.py
```

### Flujo de Uso Recomendado:

1. **Pestaña 1 - Datos de Entrada:**
   - Ingresa los datos del suelo (ej: qa=200 kPa)
   - Define la geometría inicial de la zapata (ej: 2.20x2.20 m)
   - Ingresa propiedades de materiales (ej: f'c=21 MPa)
   - Haz clic en "Guardar Datos de Entrada"
   - Observa la visualización 2D de la zapata

2. **Pestaña 2 - Cargas:**
   - Agrega casos de carga (Muerta, Viva, Viento)
   - Haz clic en "Generar Combinaciones ACI/ASCE-7"
   - Observa cómo se dibuja el diagrama 3D con las cargas aplicadas
   - Las flechas rojas muestran la carga axial N
   - Las flechas verdes/naranjas muestran cortantes Vx/Vy

3. **Pestaña 3 - Análisis:**
   - Ajusta los parámetros de estabilidad si es necesario
   - Haz clic en "Ejecutar Análisis"
   - Revisa las tablas de presiones y estabilidad
   - Observa los gráficos de comparación vs límites
   - Verifica el diseño estructural en la tercera sección

4. **Pestaña 4 - Optimización:**
   - Define el rango de búsqueda (B, L, h)
   - Selecciona el objetivo (minimizar área es lo más común)
   - Haz clic en "Ejecutar Optimización"
   - Observa la geometría óptima en 3D
   - Revisa el Top 10 de soluciones factibles

5. **Pestaña 5 - Resultados:**
   - Descarga el reporte en el formato deseado
   - Excel: ideal para análisis posterna
   - PDF: para presentaciones profesionales
   - Word: para incorporar en informes detallados


## Pruebas Realizadas ✓

Se ejecutaron pruebas completas del flujo:
- [1/5] Guardado de datos de entrada: OK
- [2/5] Agregación de cargas y generación de combinaciones: OK
- [3/5] Análisis completo (presiones, estabilidad, diseño): OK
- [4/5] Optimización de geometría: OK
- [5/5] Validación de visualizaciones: OK

**Resultado final:** TODAS LAS PRUEBAS PASARON EXITOSAMENTE


## Características Adicionales de Visualización

### En tiempo real:
- Los gráficos se actualizan automáticamente al guardar datos
- Los diagramas 3D son rotables e interactivos (click y arrastra)
- Las tablas se actualizan con cada operación

### Visualizaciones disponibles:
- **2D (Vista superior):** Geometría de la zapata con dimensiones
- **3D (Cargas):** Diagrama de fuerzas y momentos aplicados
- **Gráficos de barras:** Presiones vs límite de capacidad
- **Gráficos de barras:** Factores de seguridad vs mínimos requeridos
- **3D (Óptima):** Geometría optimizada con las mejores dimensiones


## Notas Importantes

1. **Resolución del Pantalla:** La aplicación se redimensiona automáticamente. Para mejor experiencia se recomienda una resolución de al menos 1400x900 píxeles.

2. **Todos los ejes están claramente etiquetados:**
   - Eje X (verde): Dirección horizontal
   - Eje Y (púrpura): Dirección vertical (en planta)
   - Eje Z (Negro): Dirección vertical (en alzado - solo en 3D)

3. **Unidades:** Todo está en unidades SI (metros, kilopascales, megapascales)

4. **Exactitud:** Los cálculos siguen norma ACI 318-19 y ASCE-7

5. **Combinaciones:** Se generan automáticamente 23 combinaciones de carga según ACI/ASCE-7 con factores de carga correctos


## Comparativa: Tkinter vs Streamlit

| Aspecto | Tkinter | Streamlit |
|---------|---------|-----------|
| Instalación | Incluido en Python | Requiere instalación |
| Ejecución | Local solo | Local o en servidor |
| Visualización | Excelente (matplotlib integrado) | Excelente (también matplotlib) |
| Interfaz | Clásica/Desktop | Web moderna |
| Comparto con otros | Necesita estar en red | Fácil (URL pública) |
| Velocidad | Rápida | Rápida |

**Conclusión:** Tkinter es ideal para uso local/empresarial sin conexión constante a internet.
