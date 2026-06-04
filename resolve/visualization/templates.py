import plotly.graph_objects as go
import plotly.io as pio


axes = dict(
    showgrid=False,
    linecolor="rgb(120, 120, 120)",
    linewidth=1,
    showline=True,
    ticks="outside",
    tickcolor="rgb(120, 120, 120)",
    mirror=True,
)

pio.templates["e3"] = go.layout.Template(
    layout=go.Layout(
        font=dict(family="Arial", size=18, color="rgb(120, 120, 120)"),
        title=dict(
            font=dict(
                # size=32,
                color="rgb(3, 78, 110)",
            ),
            x=0.05,
            y=0.95,
            xanchor="left",
            yanchor="bottom",
        ),
        xaxis=axes,
        yaxis=axes,
        margin=dict(t=40, b=100, r=40, l=70),
    )
)

pio.templates["5.4x12.32"] = go.layout.Template(
    layout=go.Layout(
        height=5.4 * 144,
        width=12.32 * 144,
    )
)

pio.templates.default = "e3"
