# Machine Learning Studio

Data Science Studio is Ronin's local-first vertical plugin for classical data science. It models a lab as datasets, preparation steps, experiment requests, runs, evaluations and registered model versions. The UI depends on the `MLBackend` protocol, so the execution engine can later be replaced by Spark ML, XGBoost, a remote Ronin worker or a managed service without changing lab definitions.

The first adapter is `local.sklearn`, backed by Ronin's existing deterministic tabular runtime. It intentionally starts with classification and regression baselines and portable non-executable artifacts. Planned slices are profiling/quality checks, visual preparation recipes, model comparison, explainability, champion promotion, batch scoring and scheduled retraining.

Product ideas adapted from Dataiku's documented Flow and Visual ML concepts: a visual project flow, reusable feature handling, one task per prediction objective, automatic baseline comparison, model documentation and a clear transition from experiment to saved model. See [Dataiku Visual ML](https://developer.dataiku.com/latest/concepts-and-examples/ml.html), [Visual recipes](https://doc.dataiku.com/dss/latest/other_recipes/index.html), and [Automated ML](https://doc.dataiku.com/dss/latest/machine-learning/auto-ml.html).
