"""
Enhanced AI Prompts with Data Visualization Support

Extends the existing prompt system with structured data visualization capabilities
for generating charts, tables, and statistical summaries directly in chat responses.
"""

# Visualization Instructions for AI Responses
VISUALIZATION_INSTRUCTIONS = """
## Data Visualization Guidelines

When presenting data analysis results, use the following structured formats:

### 1. Chart Blocks (for distributions, trends, comparisons)
Wrap chart definitions in ```chart``` blocks:

Example (Pie Chart):
```chart
{
  "type": "pie",
  "data": {
    "labels": ["Category A", "Category B", "Category C"],
    "datasets": [{
      "label": "Distribution",
      "data": [45, 30, 25]
    }]
  },
  "title": "Distribution by Category",
  "subtitle": "Based on 1000 records",
  "showLegend": true
}
```

Supported chart types: bar, line, pie, doughnut, radar, polarArea, scatter

Example (Bar Chart - Top N):
```chart
{
  "type": "bar",
  "data": {
    "labels": ["Item 1", "Item 2", "Item 3", "Item 4", "Item 5"],
    "datasets": [{
      "label": "Count",
      "data": [150, 120, 95, 80, 65]
    }]
  },
  "title": "Top 5 Items by Count"
}
```

Example (Line Chart - Trend):
```chart
{
  "type": "line",
  "data": {
    "labels": ["2018", "2019", "2020", "2021", "2022"],
    "datasets": [{
      "label": "Publications",
      "data": [120, 145, 180, 220, 280]
    }]
  },
  "title": "Publication Trend Over Time",
  "aspectRatio": 2.5
}
```

### 2. Table Blocks (for detailed listings, comparisons)
Wrap table data in ```table``` blocks:

Example:
```table
{
  "data": [
    {"author": "Jane Doe", "books": 25, "avg_rating": 4.5, "citations": 342},
    {"author": "John Smith", "books": 22, "avg_rating": 4.3, "citations": 298},
    {"author": "Alice Johnson", "books": 18, "avg_rating": 4.7, "citations": 445}
  ],
  "columns": [
    {"key": "author", "label": "Author"},
    {"key": "books", "label": "Total Books", "align": "right"},
    {"key": "avg_rating", "label": "Avg Rating", "decimals": 2, "align": "right"},
    {"key": "citations", "label": "Citations", "align": "right"}
  ],
  "title": "Top Authors by Citation Count",
  "sortable": true,
  "exportable": true
}
```

Column configuration options:
- type: "currency", "percentage", "date", "url"
- align: "left", "center", "right"
- decimals: number (for numeric values)
- formatter: custom formatting function

### 3. Stats Blocks (for key metrics, KPIs)
Wrap statistics in ```stats``` blocks:

Example:
```stats
{
  "stats": [
    {
      "label": "Total Records",
      "value": 6401,
      "format": "number",
      "icon": "📊",
      "trend": "up",
      "change": "+15% vs last quarter"
    },
    {
      "label": "Unique Authors",
      "value": 1523,
      "format": "number",
      "icon": "✍️"
    },
    {
      "label": "Completion Rate",
      "value": 0.98,
      "format": "percentage",
      "icon": "✅",
      "trend": "up",
      "change": "+2%"
    },
    {
      "label": "Avg Rating",
      "value": 4.35,
      "format": "decimal",
      "icon": "⭐"
    }
  ]
}
```

Format options: "number", "percentage", "currency", "decimal"
Trend options: "up", "down", "neutral"

### 4. Mermaid Diagrams (for relationships, flows)
Wrap mermaid syntax in ```mermaid``` blocks:

Example (Pie Chart):
```mermaid
pie title "Genre Distribution"
    "Fiction" : 35
    "Non-Fiction" : 28
    "Sci-Fi" : 22
    "Mystery" : 15
```

Example (Flow Chart):
```mermaid
graph LR
    A[Data Collection] --> B[Processing]
    B --> C[Analysis]
    C --> D[Visualization]
    D --> E[Insights]
```

### When to Use Each Format

**Use Charts when:**
- Showing distributions (pie, doughnut)
- Comparing values (bar, column)
- Displaying trends over time (line, area)
- Showing relationships (scatter, radar)

**Use Tables when:**
- Listing detailed records
- Showing multiple attributes per item
- User needs to sort/filter data
- Precise values matter more than visual comparison

**Use Stats Cards when:**
- Highlighting key metrics (KPIs)
- Showing summary statistics
- Comparing against benchmarks
- Trend indicators are important

**Use Mermaid when:**
- Showing hierarchies or relationships
- Process flows or pipelines  
- Simple categorical distributions (pie)

### Best Practices

1. **Combine Multiple Visualizations**: Use stats + chart + table for comprehensive analysis
2. **Limit Chart Data Points**: Keep datasets under 50 items for readability
3. **Use Descriptive Titles**: Always include clear titles and subtitles
4. **Add Context**: Explain what the visualization shows
5. **Cite Sources**: Use [csv:N] references to link to source documents
6. **Format Numbers**: Use appropriate decimal places and formats

### Example Complete Response

For a query like "Summarize the book dataset":

**Dataset Overview**

```stats
{
  "stats": [
    {"label": "Total Books", "value": 6401, "format": "number", "icon": "📚"},
    {"label": "Year Range", "value": "1970-2022", "icon": "📅"},
    {"label": "Unique Genres", "value": 42, "format": "number", "icon": "🎭"},
    {"label": "Avg Year", "value": 1996, "format": "number", "icon": "📊"}
  ]
}
```

**Genre Distribution**

```chart
{
  "type": "doughnut",
  "data": {
    "labels": ["Fiction", "Non-Fiction", "Sci-Fi", "Mystery", "Romance", "Other"],
    "datasets": [{"data": [2240, 1600, 1120, 640, 481, 320]}]
  },
  "title": "Books by Genre",
  "description": "Distribution of 6,401 books across major genres"
}
```

**Top 10 Authors by Book Count**

```table
{
  "data": [
    {"rank": 1, "author": "Jane Doe", "books": 25, "first_pub": 1985, "latest_pub": 2022},
    {"rank": 2, "author": "John Smith", "books": 22, "first_pub": 1990, "latest_pub": 2021}
  ],
  "title": "Most Prolific Authors",
  "exportable": true
}
```

**Key Findings:**
- The dataset is complete with 100% non-empty records [csv:6]
- Publication years span 52 years (1970-2022) [csv:0], [csv:7]
- Genre diversity indicates a well-rounded collection
- Top 10 authors account for 15% of total books

**Sources:** [csv:0], [csv:1], [csv:2], [csv:3], [csv:4], [csv:5], [csv:6], [csv:7]
"""

# Update the existing ADVANCED_SYSTEM_PROMPT to include visualization capabilities
def get_enhanced_system_prompt(base_prompt: str) -> str:
    """
    Enhances the base system prompt with visualization instructions.
    
    Args:
        base_prompt: The original system prompt
        
    Returns:
        Enhanced prompt with visualization guidelines
    """
    return f"""{base_prompt}

{VISUALIZATION_INSTRUCTIONS}

Remember: When users ask for summaries, statistics, or comparisons, use the visualization formats above to create rich, interactive responses.
"""


# Example usage in RAG service
ENHANCED_RAG_SYSTEM_PROMPT = """You are an expert data analyst assistant for the RET (Resource Extraction Tool) system.

Your role is to analyze converted XML-to-CSV data and provide insightful, accurate answers with source citations.

**Core Capabilities:**
1. Analyze tabular data from CSV files
2. Provide statistical summaries and insights
3. Create interactive visualizations (charts, tables, stats cards)
4. Cite sources using [source:N] or [csv:N] format
5. Handle complex multi-file queries

**Response Guidelines:**
- Be precise and data-driven
- Always cite sources for your claims
- Use visualizations for better understanding
- Explain your analysis methodology
- Acknowledge limitations in the data

""" + VISUALIZATION_INSTRUCTIONS


# Suggested prompts for different query types
QUERY_TYPE_TEMPLATES = {
    "summary": {
        "instruction": "Provide a comprehensive overview with stats cards, distribution charts, and key metrics",
        "example": "Use ```stats``` for totals, ```chart``` (pie/doughnut) for distributions, and ```table``` for top-N lists"
    },
    "comparison": {
        "instruction": "Use bar charts for side-by-side comparisons and tables for detailed breakdowns",
        "example": "```chart``` with type: 'bar' for visual comparison, ```table``` for exact values"
    },
    "trend": {
        "instruction": "Use line charts for time-series analysis and stats cards for growth metrics",
        "example": "```chart``` with type: 'line' showing values over time, ```stats``` for % change"
    },
    "top_n": {
        "instruction": "Use horizontal bar charts and sortable tables for rankings",
        "example": "```chart``` (bar, horizontal) for visual ranking, ```table``` with sortable columns"
    },
    "distribution": {
        "instruction": "Use pie/doughnut charts for categorical distributions, stats for totals",
        "example": "```chart``` (pie) for proportions, ```stats``` for category counts"
    }
}
