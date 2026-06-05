############################################################
# TOMTOM - SOLO DESCARGA DE TRAFFIC FLOW POR NODO
# Ajustado a tabla:
# id_nodo | nombre_nodo | Categoria | Lat | Lon | prioridad
# activo | zona | Barrios que colinda | notas | Columna1
############################################################

install.packages("readxl")
install.packages("httr2")
install.packages("openxlsx")
suppressPackageStartupMessages({
  library(dplyr)
  library(readxl)
  library(httr2)
  library(purrr)
  library(openxlsx)
  library(stringr)
  library(tibble)
})

############################################################
# 1) CONFIGURACIÓN
############################################################
dir_base <- "C:/Users/EDGAR/Downloads/NODOS/Proyecto"
file_excel <- file.path(dir_base, "nodos.xlsx")

TT_KEY <- "bcbnmCtwNGBmYA1IaatQjOh9gEfCthe1"

URL_FLOWBASE <- "https://api.tomtom.com/traffic/services/4/flowSegmentData"
tz_local <- "America/Bogota"
consulta_ts <- as.POSIXct(Sys.time(), tz = tz_local)

############################################################
# 2) FUNCIONES AUXILIARES
############################################################
`%||%` <- function(a, b) if (is.null(a)) b else a

safe_num <- function(x) {
  suppressWarnings(as.numeric(x))
}

clean_names_basic <- function(x) {
  x %>%
    trimws() %>%
    str_replace_all("[[:space:]]+", "_") %>%
    str_replace_all("[^[:alnum:]_]", "") %>%
    tolower()
}

to_bool_flexible <- function(x) {
  x0 <- trimws(as.character(x))
  x0[x0 %in% c("", "NA", "NaN", "NULL", "null")] <- NA_character_
  
  out <- ifelse(
    is.na(x0), NA,
    ifelse(
      toupper(x0) %in% c("TRUE", "T", "SI", "SÍ", "YES", "Y", "1"),
      TRUE,
      ifelse(
        toupper(x0) %in% c("FALSE", "F", "NO", "N", "0"),
        FALSE,
        NA
      )
    )
  )
  as.logical(out)
}

############################################################
# 3) LEER Y AJUSTAR LA TABLA DE NODOS
############################################################
nodes_raw <- read_excel(file_excel)

# Normalizar nombres reales del Excel
names(nodes_raw) <- clean_names_basic(names(nodes_raw))

# Ver cómo quedaron los nombres
cat("Columnas detectadas en el Excel:\n")
print(names(nodes_raw))

# Validar columnas mínimas
required_min <- c("id_nodo", "nombre_nodo", "categoria", "lat", "lon")
faltantes <- setdiff(required_min, names(nodes_raw))
if (length(faltantes) > 0) {
  stop("Faltan columnas requeridas en el Excel: ", paste(faltantes, collapse = ", "))
}

# Si no existen algunas columnas opcionales, crearlas
opcionales <- c("prioridad", "activo", "zona", "barrios_que_colinda", "notas", "columna1")
for (nm in opcionales) {
  if (!nm %in% names(nodes_raw)) {
    nodes_raw[[nm]] <- NA
  }
}

# Ajuste de tipos y lógica de activación
nodes <- nodes_raw %>%
  mutate(
    id_nodo = as.character(id_nodo),
    nombre_nodo = as.character(nombre_nodo),
    categoria = as.character(categoria),
    prioridad = as.character(prioridad),
    zona = as.character(zona),
    barrios_que_colinda = as.character(barrios_que_colinda),
    notas = as.character(notas),
    lat = safe_num(lat),
    lon = safe_num(lon),
    activo_txt = to_bool_flexible(activo),
    activo_col1 = case_when(
      is.na(safe_num(columna1)) ~ NA,
      safe_num(columna1) == 1 ~ TRUE,
      safe_num(columna1) == 0 ~ FALSE,
      TRUE ~ NA
    ),
    activo_final = dplyr::coalesce(activo_txt, activo_col1, TRUE)
  ) %>%
  filter(!is.na(lat), !is.na(lon)) %>%
  filter(activo_final == TRUE)

if (nrow(nodes) == 0) {
  stop("No hay nodos activos con coordenadas válidas para consultar.")
}

cat("\nTotal nodos activos a consultar:", nrow(nodes), "\n")

############################################################
# 4) FUNCIÓN PARA CONSULTAR TRAFFIC FLOW
############################################################
flow_one <- function(lat, lon, zoom = 10, style = "relative", unit = "KMPH") {
  
  url <- sprintf("%s/%s/%s/json", URL_FLOWBASE, style, zoom)
  
  req_f <- request(url) %>%
    req_url_query(
      key = TT_KEY,
      point = sprintf("%.6f,%.6f", lat, lon),
      unit = unit
    ) %>%
    req_timeout(30) %>%
    req_error(is_error = function(resp) FALSE)
  
  resp_f <- tryCatch(
    req_perform(req_f),
    error = function(e) e
  )
  
  if (inherits(resp_f, "error")) {
    return(list(
      ok = FALSE,
      status = NA_integer_,
      j = NULL,
      msg = paste("Error de conexión:", resp_f$message)
    ))
  }
  
  status_code <- resp_status(resp_f)
  
  if (status_code >= 300) {
    return(list(
      ok = FALSE,
      status = status_code,
      j = NULL,
      msg = resp_body_string(resp_f)
    ))
  }
  
  j <- tryCatch(
    resp_body_json(resp_f, simplifyVector = TRUE),
    error = function(e) NULL
  )
  
  if (is.null(j)) {
    return(list(
      ok = FALSE,
      status = status_code,
      j = NULL,
      msg = "No se pudo parsear la respuesta JSON"
    ))
  }
  
  list(
    ok = TRUE,
    status = status_code,
    j = j,
    msg = NA_character_
  )
}

############################################################
# 5) CONSULTAR FLOW PARA CADA NODO
############################################################
flows <- purrr::pmap(
  list(nodes$lat, nodes$lon),
  flow_one
)

flow_df <- tibble(
  id_nodo = nodes$id_nodo,
  nombre_nodo = nodes$nombre_nodo,
  categoria = nodes$categoria,
  prioridad = nodes$prioridad,
  zona = nodes$zona,
  barrios_que_colinda = nodes$barrios_que_colinda,
  notas = nodes$notas,
  lat = nodes$lat,
  lon = nodes$lon,
  activo_final = nodes$activo_final,
  ok = map_lgl(flows, "ok"),
  http_status = map_int(flows, ~ ifelse(is.null(.x$status), NA_integer_, .x$status)),
  currentSpeed = map_dbl(flows, ~ safe_num(.x$j$flowSegmentData$currentSpeed %||% NA_real_)),
  freeFlowSpeed = map_dbl(flows, ~ safe_num(.x$j$flowSegmentData$freeFlowSpeed %||% NA_real_)),
  currentTravelTime = map_dbl(flows, ~ safe_num(.x$j$flowSegmentData$currentTravelTime %||% NA_real_)),
  freeFlowTravelTime = map_dbl(flows, ~ safe_num(.x$j$flowSegmentData$freeFlowTravelTime %||% NA_real_)),
  confidence = map_dbl(flows, ~ safe_num(.x$j$flowSegmentData$confidence %||% NA_real_)),
  roadClosure = map_chr(flows, ~ as.character(.x$j$flowSegmentData$roadClosure %||% NA)),
  frc = map_chr(flows, ~ as.character(.x$j$flowSegmentData$frc %||% NA)),
  currentSpeed_unconfined = map_dbl(flows, ~ safe_num(.x$j$flowSegmentData$currentSpeedUncapped %||% NA_real_)),
  consultation_time = format(consulta_ts, "%Y-%m-%d %H:%M:%S"),
  error_msg = map_chr(flows, ~ as.character(.x$msg %||% NA_character_))
) %>%
  mutate(
    delay_abs_seg = ifelse(
      !is.na(currentTravelTime) & !is.na(freeFlowTravelTime),
      currentTravelTime - freeFlowTravelTime,
      NA_real_
    ),
    delay_rel_pct = ifelse(
      !is.na(currentTravelTime) & !is.na(freeFlowTravelTime) & freeFlowTravelTime > 0,
      100 * (currentTravelTime - freeFlowTravelTime) / freeFlowTravelTime,
      NA_real_
    ),
    velocidad_ratio = ifelse(
      !is.na(currentSpeed) & !is.na(freeFlowSpeed) & freeFlowSpeed > 0,
      currentSpeed / freeFlowSpeed,
      NA_real_
    )
  )

############################################################
# 6) EXPORTAR RESULTADOS
############################################################
stamp <- format(consulta_ts, "%Y%m%d_%H%M%S")

out_xlsx <- file.path(dir_base, paste0("TomTom_TrafficFlow_", stamp, ".xlsx"))
out_csv <- file.path(dir_base, paste0("TomTom_TrafficFlow_", stamp, ".csv"))

wb <- createWorkbook()

addWorksheet(wb, "Traffic_Flow")
writeDataTable(wb, "Traffic_Flow", flow_df)
setColWidths(wb, "Traffic_Flow", cols = 1:ncol(flow_df), widths = "auto")

addWorksheet(wb, "Resumen")
resumen_df <- tibble(
  indicador = c(
    "fecha_consulta",
    "hora_consulta",
    "total_nodos_consultados",
    "consultas_ok",
    "consultas_error",
    "velocidad_actual_promedio",
    "velocidad_libre_promedio",
    "delay_promedio_seg",
    "delay_promedio_pct",
    "confianza_promedio"
  ),
  valor = c(
    as.character(as.Date(consulta_ts)),
    format(consulta_ts, "%H:%M:%S"),
    nrow(flow_df),
    sum(flow_df$ok, na.rm = TRUE),
    sum(!flow_df$ok, na.rm = TRUE),
    round(mean(flow_df$currentSpeed, na.rm = TRUE), 2),
    round(mean(flow_df$freeFlowSpeed, na.rm = TRUE), 2),
    round(mean(flow_df$delay_abs_seg, na.rm = TRUE), 2),
    round(mean(flow_df$delay_rel_pct, na.rm = TRUE), 2),
    round(mean(flow_df$confidence, na.rm = TRUE), 4)
  )
)
writeDataTable(wb, "Resumen", resumen_df)
setColWidths(wb, "Resumen", cols = 1:2, widths = "auto")

saveWorkbook(wb, out_xlsx, overwrite = TRUE)
write.csv(flow_df, out_csv, row.names = FALSE, fileEncoding = "UTF-8")

############################################################
# 7) MENSAJES FINALES
############################################################
cat("\n========================================\n")
cat("PROCESO FINALIZADO\n")
cat("Archivo Excel:", out_xlsx, "\n")
cat("Archivo CSV :", out_csv, "\n")
cat("Hora consulta:", format(consulta_ts, "%Y-%m-%d %H:%M:%S"), "\n")
cat("Nodos consultados:", nrow(flow_df), "\n")
cat("Consultas OK:", sum(flow_df$ok, na.rm = TRUE), "\n")
cat("Consultas con error:", sum(!flow_df$ok, na.rm = TRUE), "\n")
cat("========================================\n")
