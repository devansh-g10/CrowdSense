"""Read only the small, explicitly named JSON/CSV exports; no new evaluation."""
import csv

from .config import Settings
from .schemas import Comparison, ModelMetadata, PeakHour, TestMetrics, Weekly


class ExportRepository:
    def __init__(self, settings: Settings):
        self.settings = settings

    def metadata(self):
        return ModelMetadata.model_validate_json(
            (self.settings.data_dir / 'model_metadata.json').read_text(encoding='utf-8'))

    def _csv(self, filename, schema):
        # Filenames come only from this module, never from HTTP input.
        with (self.settings.data_dir / filename).open(encoding='utf-8', newline='') as stream:
            values = [schema.model_validate(row) for row in csv.DictReader(stream)]
        if not values:
            raise ValueError(f'Empty required export: {filename}')
        return values

    def weekly(self):
        return self._csv('weekly_analysis.csv', Weekly)

    def peak_hours(self):
        return self._csv('peak_analysis.csv', PeakHour)

    def performance(self):
        metrics = self._csv('test_metrics.csv', TestMetrics)
        if len(metrics) != 1:
            raise ValueError('Expected exactly one test metrics row')
        return {'test_metrics': metrics[0],
                'model_comparison': self._csv('model_comparison.csv', Comparison),
                'sources': ['test_metrics.csv', 'model_comparison.csv']}

    def verify(self):
        self.metadata()
        self.weekly()
        self.peak_hours()
        self.performance()
