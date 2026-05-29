from kit.core.component import BaseComponent


class BaseOutageDistribution(BaseComponent):
    """
    Represents the probability distribution of generator outages used
    in a Loss of Load Probability (LOLP) model.

    This object captures the stochastic availability of generating units
    by assigning probabilities to different levels of available capacity.
    It is typically derived from unit-specific outage rates (forced outage
    rates, mean time to repair, etc.) and aggregated to represent system-level
    capacity risk.
    """
