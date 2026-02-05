## EventExport ZIP Import (agility.exchange.eventexport.v1)

Dieses Dokument beschreibt ein minimales Beispiel für den Import eines Portal-EventExport ZIPs
inklusive Startnummern und Zeitplan.

### Beispiel-Dateistruktur

```
eventexport.zip
├─ manifest.json
├─ event.json
├─ entities.json
├─ registrations.json
├─ start_numbers.json
└─ schedule.json
```

### Minimaler Inhalt

**manifest.json**
```json
{ "schema": "agility.exchange.eventexport.v1" }
```

**event.json**
```json
{
  "event": {
    "name": "Beispielturnier",
    "date": "2025-05-10",
    "club_number": "199",
    "event_number": "12314"
  }
}
```

**entities.json**
```json
{
  "handlers": [
    { "external_id": "handler_1", "firstname": "Max", "lastname": "Mustermann" }
  ],
  "dogs": [
    { "license_no": "12345", "dog_name": "Uma", "handler_external_id": "handler_1", "category_code": "Small", "class_level": "1" }
  ]
}
```

**registrations.json**
```json
{
  "registrations": [
    {
      "registration_external_id": "reg_1",
      "license_no": "12345",
      "dog_name": "Uma",
      "handler_first_name": "Max",
      "handler_last_name": "Mustermann",
      "discipline": "Agility",
      "category_code": "Small",
      "class_level": "1"
    }
  ]
}
```

**start_numbers.json**
```json
{
  "locked": true,
  "start_numbers": [
    { "registration_external_id": "reg_1", "license_no": "12345", "start_no": 101 }
  ]
}
```

**schedule.json**
```json
{
  "blocks": [
    {
      "ring": 1,
      "start_at": "2025-05-10T08:00:00",
      "discipline": "Agility",
      "category_code": "Small",
      "class_level": "1",
      "notes": "Eröffnungs-Block"
    }
  ]
}
```

### Erwartetes Ergebnis

- Startnummern werden den Teilnehmern zugewiesen (inkl. `start_numbers_locked`).
- Zeitplanblöcke erscheinen im Zeitplan (Planung + Druck).
- Import-Log zeigt:
  - „Startnummern importiert: X (locked: true/false)“
  - „Zeitplanblöcke importiert: Y“
