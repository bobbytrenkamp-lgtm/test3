args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 9) stop("expected nine governed arguments")
required <- c("jsonlite", "sandwich")
if (any(!vapply(required, requireNamespace, logical(1), quietly = TRUE))) {
  message("Optional open-source R packages jsonlite and sandwich are required")
  quit(status = 3)
}
input <- read.csv(args[[1]], check.names = FALSE, stringsAsFactors = FALSE)
output <- args[[2]]
target <- args[[3]]
features <- strsplit(args[[4]], ",", fixed = TRUE)[[1]]
entity <- args[[5]]
time <- args[[6]]
entity_effects <- identical(args[[7]], "true")
time_effects <- identical(args[[8]], "true")
covariance <- args[[9]]
terms <- features
if (entity_effects) terms <- c(terms, sprintf("factor(`%s`)", entity))
if (time_effects) terms <- c(terms, sprintf("factor(`%s`)", time))
formula <- as.formula(sprintf("`%s` ~ %s", target, paste(terms, collapse = " + ")))
fit <- lm(formula, data = input)
vcov_result <- if (covariance == "hc1") sandwich::vcovHC(fit, type = "HC1") else if (covariance == "cluster_entity") sandwich::vcovCL(fit, cluster = input[[entity]], type = "HC1") else vcov(fit)
result <- list(
  status = "completed",
  coefficients = as.list(unname(coef(fit))),
  coefficient_names = names(coef(fit)),
  standard_errors = as.list(unname(sqrt(diag(vcov_result)))),
  r_squared = unname(summary(fit)$r.squared),
  adjusted_r_squared = unname(summary(fit)$adj.r.squared),
  sample_size = nobs(fit),
  covariance = covariance
)
jsonlite::write_json(result, output, auto_unbox = TRUE, digits = 17, pretty = TRUE)
