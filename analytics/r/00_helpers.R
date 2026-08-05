warning_label <- "FICTIONAL SYNTHETIC MODEL — NOT FOR REAL UNDERWRITING"
assert_columns <- function(x, required) { missing <- setdiff(required, names(x)); if (length(missing)) stop(paste("Missing columns:", paste(missing, collapse=", "))) }
write_output <- function(x, name) { dir.create("analytics/outputs/fictional", recursive=TRUE, showWarnings=FALSE); write.csv(x, file.path("analytics/outputs/fictional", name), row.names=FALSE, na="") }
