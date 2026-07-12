import re

with open("src/arbitrator/presentation/static/partials/pages/monitors.html", "r", encoding="utf-8") as f:
    content = f.read()

# Make the card 75vh and the chart flexible
target_card_style = 'class="live-card" style="border: 1px solid #1e293b; border-radius: 8px; overflow: hidden; background: #1f2937; color: #d1d5db; width: 450px; display: flex; flex-direction: column; font-family: sans-serif;"'
new_card_style = 'class="live-card" style="border: 1px solid #1e293b; border-radius: 8px; overflow: hidden; background: #1f2937; color: #d1d5db; width: 450px; height: 75vh; display: flex; flex-direction: column; font-family: sans-serif;"'

content = content.replace(target_card_style, new_card_style)

# Make spread tracking container flex: 1 and canvas container flex: 1
target_spread_style = 'class="lc-spread-tracking" style="padding: 16px; border-top: 1px solid #374151; font-size: 0.9em;"'
new_spread_style = 'class="lc-spread-tracking" style="padding: 16px; border-top: 1px solid #374151; font-size: 0.9em; flex: 1; display: flex; flex-direction: column;"'
content = content.replace(target_spread_style, new_spread_style)

target_canvas_container = '<div style="height: 100px; width: 100%; position: relative;">'
new_canvas_container = '<div style="flex: 1; width: 100%; position: relative; min-height: 100px;">'
content = content.replace(target_canvas_container, new_canvas_container)

with open("src/arbitrator/presentation/static/partials/pages/monitors.html", "w", encoding="utf-8") as f:
    f.write(content)
