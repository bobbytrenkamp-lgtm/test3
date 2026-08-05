source("analytics/r/01_validate_inputs.R")
panel$period_index <- seq_len(nrow(panel))
features <- panel[,c("period_index","vacancy_rate","rent_growth_12m")]
