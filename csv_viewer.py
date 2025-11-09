from pathlib import Path
import pandas as pd
from pandas.api.types import is_numeric_dtype
import pandasql as pdsql
import dash
from dash import html, dcc, Output, Input, State, dash_table
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import re
import base64
import io

app = dash.Dash(
    __name__, external_stylesheets=[dbc.themes.DARKLY], assets_folder="assets"
)


app.layout = dbc.Container(
    [
        dcc.Store(
            id="store",
            data={
                "df": None,
                "last_submit": 1,
                "last_click": 1,
                "query": "SELECT * FROM df",
                "last_click_row": 1,
            },
        ),
        html.H1("CSV Visualization"),
        html.H2(id="file-title"),
        dbc.Row(
            dcc.Upload(
                html.A("Select CSV file"),
                id="upload-csv",
                style={
                    "width": "100%",
                    "height": "60px",
                    "lineHeight": "60px",
                    "borderWidth": "1px",
                    "borderStyle": "dashed",
                    "borderRadius": "5px",
                    "textAlign": "center",
                    "margin": "10px",
                },
                multiple=False,
            )
        ),
        dbc.Row(
            [
                dbc.Col(
                    html.Div(
                        dbc.Input(
                            id="query-input",
                            size="lg",
                            type="text",
                        )
                    ),
                    style={"margin": 5},
                ),
                dbc.Col(
                    html.Div(
                        dbc.Button("execute", id="execute-btn", size="lg", n_clicks=0)
                    ),
                    width=1,
                ),
            ]
        ),
        dbc.Row(html.Div(html.H2(id="error", style={"color": "red"}))),
        dbc.Row(html.Div(id="cell-display")),
        dbc.Row(
            html.Div(
                id="row-display",
            )
        ),
        dbc.Row(
            [
                html.Div(id="export-div"),
                dcc.Download(id="download-csv"),
            ]
        ),
        dbc.Row(html.Div(id="main-table")),
        dbc.Row(html.Div(id="graph-area")),
    ],
    fluid=True,
)


@app.callback(
    Output("store", "data"),
    Output("error", "children"),
    Output("file-title", "children"),
    Input("upload-csv", "contents"),
    State("upload-csv", "filename"),
    State("store", "data"),
    prevent_initial_call=True,
)
def load_data(file_content, file_name, data):
    if file_content is None:
        return (data, "CSV not loaded", "")

    content_type, content_string = file_content.split(",")
    if content_type != "data:text/csv;base64":
        data["df"] = None
        return (data, "Invalid CSV file", "")
    decoded = base64.b64decode(content_string)
    try:
        df = pd.read_csv(io.StringIO(decoded.decode("utf-8")))
        data["df"] = df.to_json(date_format="iso", orient="split")
        data["query"] = "SELECT * FROM df"
        return data, "", file_name
    except Exception as e:
        data["df"] = None
        return data, f"Error loading {file_name}: {e}", ""


@app.callback(
    Output("store", "data", allow_duplicate=True),
    Output("error", "children", allow_duplicate=True),
    Input("execute-btn", "n_clicks"),
    Input("query-input", "n_submit"),
    State("query-input", "value"),
    State("store", "data"),
    prevent_initial_call=True,
)
def handle_query(btn, submit, query, data):
    if data["df"] is None:
        return data, "CSV not loaded"
    if submit != data["last_submit"] and btn != data["last_click"]:
        return data, ""
    elif submit == data["last_submit"]:
        data["last_submit"] = submit + 1
    elif btn == data["last_click"]:
        data["last_click"] = btn + 1
    if query == "" or query is None:
        data["query"] = "SELECT * FROM df"
        return data, ""
    else:
        try:
            df = pd.read_json(io.StringIO(data["df"]), orient="split")
            tmp = pdsql.sqldf(query)
            data["query"] = query
            return data, ""
        except Exception as e:
            data["query"] = "SELECT * FROM df"
            return data, f"Error: {e}"


@app.callback(
    Output("export-div", "children"),
    Input("store", "data"),
    prevent_initial_call=True,
)
def create_export_button(data):
    if data["df"] is None:
        return ""
    return dbc.Button(
        "export",
        id="export-btn",
        size="lg",
        n_clicks=0,
        style={"margin": "5px"},
    )


@app.callback(
    Output("main-table", "children"),
    Input("store", "data"),
    prevent_initial_call=True,
)
def create_table(data):
    if data["df"] is None:
        return ""

    df = pd.read_json(io.StringIO(data["df"]), orient="split")
    query = data["query"]
    filtered_df = pdsql.sqldf(query)
    # table = dbc.Table.from_dataframe(
    #     filtered_df, striped=True, bordered=True, hover=True
    # )
    table = dash_table.DataTable(
        id="table",
        data=filtered_df.to_dict("records"),
        columns=[{"name": i, "id": i} for i in filtered_df.columns],
        page_size=15,  # built-in pagination
        page_current=0,
        style_table={"overflowX": "auto", "font-size": "20px"},
        style_cell={"overflowX": "auto", "text-align": "left"},
    )
    return table


@app.callback(
    Output("cell-display", "children"),
    Input("table", "active_cell"),
    State("store", "data"),
    State("table", "page_current"),
    State("table", "page_size"),
    prevent_initial_call=True,
)
def update_cell_display(cell, data, cur_page, page_size):
    if cell is None:
        return ""
    df = pd.read_json(io.StringIO(data["df"]), orient="split")
    query = data["query"]

    index = (cur_page * page_size) + cell["row"]
    filtered_df = pdsql.sqldf(query)
    value = filtered_df.iloc[index][cell["column_id"]]
    if "group by" in query.lower():
        return dbc.Row(
            [
                dbc.Col(
                    html.Div(
                        f"{cell['column_id']}: {value}",
                        style={
                            "font-size": "20px",
                            "margin": "5",
                            "margin-bottom": "20px",
                        },
                    )
                ),
            ]
        )
    else:
        return dbc.Row(
            [
                dbc.Col(html.Div(f"{cell['column_id']}: {value}")),
                dbc.Col(
                    html.Div(
                        dbc.Button(
                            "Show entire row", id="show-btn", size="lg", n_clicks=0
                        ),
                        style={"float": "right"},
                    ),
                    width=2,
                ),
            ],
            style={"font-size": "20px", "margin": "5", "margin-bottom": "20px"},
        )


@app.callback(
    Output("graph-area", "children"),
    Input("store", "data"),
    prevent_initial_call=True,
)
def create_graph(data):
    if data["df"] is None:
        return ""
    df = pd.read_json(io.StringIO(data["df"]), orient="split")
    query = data["query"]
    filtered_pd = pdsql.sqldf(query)

    numeric = True
    for col in filtered_pd.columns[1:]:
        if not is_numeric_dtype(filtered_pd[col]):
            numeric = False
    if len(filtered_pd.columns) >= 2 and numeric:
        x_col = filtered_pd.columns[0]
        y_cols = filtered_pd.columns[1:]
        fig = go.Figure(
            data=[
                go.Bar(name=y_col, x=filtered_pd[x_col], y=filtered_pd[y_col])
                for y_col in y_cols
            ]
        )
        fig.update_layout(barmode="group")
        colors = ["green" if "Shap" in x else "blue" for x in filtered_pd[x_col]]
        fig.update_traces(marker_color=colors)

        graph = dcc.Graph(figure=fig, style={"margin-top": "5px"})
        return graph
    else:
        return ""


@app.callback(
    Output("row-display", "children"),
    Input("show-btn", "n_clicks"),
    Input("table", "active_cell"),
    State("store", "data"),
    State("table", "page_current"),
    State("table", "page_size"),
    prevent_initial_call=True,
)
def show_column(row_clicks, cell, data, cur_page, page_size):
    if (
        row_clicks == data["last_click_row"]
        and cell is not None
        and "group by" not in data["query"].lower()
    ):
        data["last_click_row"] += 1

        query = data["query"].lower()
        matched = re.search("from", query)
        select = query[: matched.start()]
        query = query.replace(select, "SELECT * ")

        df = pd.read_json(io.StringIO(data["df"]), orient="split")
        filtered_df = pdsql.sqldf(query)

        index = (cur_page * page_size) + cell["row"]
        row = filtered_df.iloc[index].to_frame().T
        row = pd.DataFrame(row)

        table = dash_table.DataTable(
            id="row_table",
            data=row.to_dict("records"),
            columns=[{"name": i, "id": i} for i in row.columns],
            style_table={"overflowX": "auto", "font-size": "20px"},
            style_cell={"overflowX": "auto", "text-align": "left"},
            style={"font-size": "20px", "margin": "5", "margin-bottom": "20px"},
        )

        return table
    else:
        return ""


@app.callback(
    Output("download-csv", "data"),
    Input("export-btn", "n_clicks"),
    State("store", "data"),
    State("file-title", "children"),
    prevent_initial_call=True,
)
def export_csv(n_clicks, data, title):
    if n_clicks < 1:
        return ""
    df = pd.read_json(io.StringIO(data["df"]), orient="split")
    query = data["query"]
    filtered_pd = pdsql.sqldf(query)
    return dcc.send_data_frame(
        filtered_pd.to_csv, f"{title.replace('.csv','')}_export.csv", index=False
    )


if __name__ == "__main__":

    app.title = "CSV Visualizer"
    app.run(debug=False)
