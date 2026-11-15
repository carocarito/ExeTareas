# Tareas Recurrentes

Aplicación local para Windows: agenda tareas semanales o cada cierta cantidad de días, muestra un checklist diario y conserva el historial de cumplimiento en SQLite. Puedes agregar categoría, descripción y un horario opcional a cada tarea, además de elegir fechas desde la franja semanal o el calendario.

## Usar durante el desarrollo

1. Instala Python 3.10 o posterior desde [python.org](https://www.python.org/downloads/windows/) (marca **Add Python to PATH**).
2. Abre PowerShell en esta carpeta.
3. Ejecuta:

```powershell
python -m pip install -r requirements.txt
python main.py
```

## Crear el ejecutable portable

En PowerShell, desde esta carpeta:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build.ps1
```

El resultado queda en `dist\TareasRecurrentes\TareasRecurrentes.exe`. Copia **toda la carpeta** `TareasRecurrentes` a una memoria USB o a otro equipo; el archivo `data\tareas.db` se crea allí mismo y guarda las tareas y su historial.

## Uso

- **Nueva tarea:** define uno o varios días, una periodicidad cada N días, o ambos.
- Marca una tarea al terminarla. Al día siguiente aparecerá nuevamente sin marcar de forma automática, conservando la marca del día anterior como historial.
- La aplicación avisa cada 30 minutos cuando hay pendientes mientras permanece abierta. Al cerrar la ventana, la aplicación se cierra por completo.
