'use strict';

/**
 * Agility Live - Stream Deck Plugin (Browser-basiert, SDK v2)
 *
 * Drei Live-Aktionen am Ring-PC:
 *   - Startfreigabe   ->  POST /api/sd/start_release
 *   - Fehler          ->  POST /api/sd/fault
 *   - Verweigerung    ->  POST /api/sd/refusal
 *
 * Plus eine Settings-Aktion fuer Server-Konfiguration (Port + Ring).
 *
 * Settings sind Global (gelten fuer alle Tasten gleichzeitig). Standard:
 *   Host: localhost
 *   Port: 5000
 *   Ring: 1
 *
 * Inspired by VAR-Agility-Plugin (gleicher Author, gleiche Pattern).
 */

// ── State ──────────────────────────────────────────────────────────────────
let SOFTWARE_HOST = 'localhost';
let SOFTWARE_PORT = '5000';
let SOFTWARE_RING = '1';
let API_BASE      = 'http://localhost:5000';

function applySettings(host, port, ring) {
  SOFTWARE_HOST = host || 'localhost';
  SOFTWARE_PORT = String(port || '5000');
  SOFTWARE_RING = String(ring || '1');
  API_BASE = `http://${SOFTWARE_HOST}:${SOFTWARE_PORT}`;
  log(`Settings: ${API_BASE} ring=${SOFTWARE_RING}`);
}

const contexts = {};   // { [context]: { action, settings } }

// ── Stream Deck WebSocket ──────────────────────────────────────────────────
let sdWs;
let sdPort, pluginUUID, registerEvent;

function connectElgatoStreamDeckSocket(inPort, inPluginUUID, inRegisterEvent, _inInfo) {
  sdPort        = inPort;
  pluginUUID    = inPluginUUID;
  registerEvent = inRegisterEvent;

  sdWs = new WebSocket(`ws://127.0.0.1:${sdPort}`);

  sdWs.onopen = () => {
    sdSend({ event: registerEvent, uuid: pluginUUID });
    log('Stream Deck verbunden');
    sdSend({ event: 'getGlobalSettings', context: pluginUUID });
  };

  sdWs.onmessage = evt => {
    let msg;
    try { msg = JSON.parse(evt.data); } catch { return; }
    handleSDEvent(msg);
  };

  sdWs.onerror = () => log('SD Fehler');
}

function sdSend(obj) {
  if (sdWs && sdWs.readyState === WebSocket.OPEN) sdWs.send(JSON.stringify(obj));
}
function showOk(context)    { sdSend({ event: 'showOk',    context }); }
function showAlert(context) { sdSend({ event: 'showAlert', context }); }

// ── SD Events ──────────────────────────────────────────────────────────────
function handleSDEvent(msg) {
  const { event, context, action, payload } = msg;
  switch (event) {
    case 'willAppear':
      contexts[context] = { action, settings: payload?.settings || {} };
      break;
    case 'willDisappear':
      delete contexts[context];
      break;
    case 'didReceiveSettings':
      if (contexts[context]) contexts[context].settings = payload?.settings || {};
      break;
    case 'didReceiveGlobalSettings': {
      const gs = payload?.settings || {};
      applySettings(gs.host, gs.port, gs.ring);
      break;
    }
    case 'keyDown':
      onKeyDown(context, action);
      break;
  }
}

// ── Aktionen ───────────────────────────────────────────────────────────────
function onKeyDown(context, action) {
  switch (action) {
    case 'tech.z-b.agility-live.settings':
      // Ping zum aktuellen Server: zeigt OK/Alert visuell auf der Taste
      fetch(`${API_BASE}/api/sd/fault`, { method: 'OPTIONS' })
        .then(() => showOk(context))
        .catch(() => showAlert(context));
      break;

    case 'tech.z-b.agility-live.start':
      postSD(context, 'start_release');
      break;

    case 'tech.z-b.agility-live.fault':
      postSD(context, 'fault');
      break;

    case 'tech.z-b.agility-live.refusal':
      postSD(context, 'refusal');
      break;
  }
}

function postSD(context, kind) {
  fetch(`${API_BASE}/api/sd/${kind}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ring: SOFTWARE_RING, ts: Date.now() }),
  })
    .then(r => r.json().catch(() => ({})))
    .then(body => {
      if (body && body.success) {
        log(`[${kind}] ring=${SOFTWARE_RING} ok lic=${body.lic || body.current_starter_lic || '-'}`);
        showOk(context);
      } else {
        log(`[${kind}] ring=${SOFTWARE_RING} fail: ${(body && body.message) || 'unbekannt'}`);
        showAlert(context);
      }
    })
    .catch(err => {
      log(`[${kind}] ring=${SOFTWARE_RING} fetch err: ${err && err.message}`);
      showAlert(context);
    });
}

function log(msg) { console.log(`[Agility Live] ${msg}`); }
