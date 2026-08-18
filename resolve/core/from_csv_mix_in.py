from __future__ import annotations

from kit.core.custom_model import BaseCustomModel
from kit.core.from_csv_mix_in import BaseFromCSVMixIn

from resolve.core.temporal import timeseries as ts


class FromCSVMixIn(BaseFromCSVMixIn, BaseCustomModel):
    """Resolve-specific CSV mixin extending kit's BaseFromCSVMixIn.

    Overrides timeseries detection to recognise resolve's Timeseries subclasses,
    stubs out linkage base classes (resolve uses a flat linkage hierarchy that is
    declared on Component instead), and delegates timeseries resampling to the
    module-level helper in resolve.core.temporal.timeseries.
    """

    @classmethod
    def field_is_timeseries(cls, *, field_info) -> bool:
        """Return True if any type in the field annotation is a resolve Timeseries subclass.

        Overrides the kit implementation so that resolve-specific subclasses of
        ts.Timeseries (e.g. BooleanTimeseries) are correctly identified rather
        than relying on kit's __subclasses__() lookup, which only sees kit's own
        subclasses.
        """
        types = cls.get_field_type(field_info=field_info)
        return any(issubclass(t, ts.Timeseries) for t in types if isinstance(t, type))

    @classmethod
    def _linkage_base_classes(cls) -> tuple[type, ...]:
        """Return an empty tuple; resolve declares linkage classes on Component instead."""
        return ()

    # TODO: remove after timeseries refactor — EP
    def resample_ts_attributes(
        self,
        modeled_years: tuple[int, int],
        weather_years: tuple[int, int],
        resample_weather_year_attributes: bool = True,
        resample_non_weather_year_attributes: bool = True,
    ) -> dict | None:
        """Resample all timeseries attributes on this instance to their canonical frequency.

        Delegates to ts.resample_ts_attributes; see that function for full documentation.

        Args:
            modeled_years: (start_year, end_year) for non-weather-year timeseries.
            weather_years: (start_year, end_year) for weather-year timeseries.
            resample_weather_year_attributes: if False, skip weather-year timeseries.
            resample_non_weather_year_attributes: if False, skip modeled-year timeseries.

        Returns:
            dict mapping instance name to set of extrapolated attribute names, or None.
        """
        return ts.resample_ts_attributes(
            self,
            modeled_years=modeled_years,
            weather_years=weather_years,
            resample_weather_year_attributes=resample_weather_year_attributes,
            resample_non_weather_year_attributes=resample_non_weather_year_attributes,
        )
