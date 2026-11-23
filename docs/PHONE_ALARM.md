# Phone alarm (v1.2)

Your phone rings when a serious attack is detected, even when the dashboard is closed.

## Option 1: push alarm with the free ntfy app (recommended)

1. On your phone, install **ntfy** (Google Play or App Store). It's free, and you don't need an account.
2. In the dashboard, log in as **admin** and go to **Admin → Phone alarm**.
3. Click **🎲 Make a secret topic**, for example `cybershield-k3j9x2m8q1ab`. Anyone who knows the topic gets your alarms, so keep it secret.
4. In the ntfy app, tap **+**, type the same topic (server `ntfy.sh`) and tap **Subscribe**.
5. In the app, open the topic → **Notification settings** → choose **max/urgent priority** and a loud sound.
   On Android you can also allow **"Override Do Not Disturb"**.
6. In the dashboard: paste the topic, click **Save**, then **🔔 Send test alarm**. Your phone should ring
   within a few seconds. Saving a topic switches the **Automatic alarm** on.
7. From then on, **every simulated attack rings the phone by itself** (no button to click). "Ring for: every
   attack" is the default; network faults (a link or node going down) don't ring.
7. Test it with a real (simulated) attack: Security tab → **Flood attack**, or `attack flood IOT-002` in the Console.

The PC running the backend needs internet. You can also set the alarm in `.env`:

```
NOTIFY_ENABLED=true
NTFY_TOPIC=cybershield-k3j9x2m8q1ab
NOTIFY_MIN_SEVERITY=high
```

(The values in `.env` are used the first time; after that, the Admin page is the place to change them.)

## Option 2: Telegram (optional)

1. In Telegram, talk to **@BotFather** → `/newbot` → copy the **bot token**.
2. Send any message to your new bot, then talk to **@userinfobot** to get your **chat ID**.
3. Admin → Phone alarm → **Telegram too** → paste the token and chat ID → Save → Send test alarm.

The token is stored in the local database and never shown again in the dashboard.

## Option 3: alarm sound on the dashboard (no internet needed)

Click **🔕 Alarm off** in the header so it shows **🔔 Alarm on**. The dashboard then plays a siren (and vibrates on
Android phones) for every high or critical alert while the page is open.

To open the dashboard on your phone (same Wi-Fi as the PC):

```
npm run dev -- --host
```

Vite prints a `Network: http://192.168.x.x:5173` address. Open it on the phone, log in, and tap **🔔**.

## What is sent

Only the alert of the **simulated** system: type, severity, device ID, description and alert number.
Sending happens in the background, so a slow internet connection never slows down detection.
Results (sent / failed, last error) are shown in Admin → Phone alarm.
