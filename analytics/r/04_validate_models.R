source("analytics/r/03_fit_models.R")
pred <- predict(model, features)
residual <- features$rent_growth_12m - pred
metrics <- data.frame(metric=c("rmse","mae","sample_size"), value=c(sqrt(mean(residual^2)),mean(abs(residual)),nrow(features)), warning=warning_label)
examples <- data.frame(period_index=features$period_index, observed=features$rent_growth_12m, predicted=pred, warning=warning_label)
