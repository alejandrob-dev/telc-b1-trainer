# Pending UI Fixes

## 1. Bottom nav overlaps content
The floating bottom navigation bar covers the bottom of page content (visible on Progress screen - chart bars and dates hidden behind nav). Need `padding-bottom` on main content area to account for nav height.

## 2. Add progress reset button
Add a "Resetear progreso" button on the Progress screen that clears all localStorage data and reloads. Should have a confirmation dialog ("¿Estás seguro? Se perderá todo el progreso.").

## 3. Translation toggle in Quiz
Add 🔤 Traducción toggle that shows Spanish translations below German text for each question and option. Must work offline (pre-baked translations). Persist toggle state in localStorage.
