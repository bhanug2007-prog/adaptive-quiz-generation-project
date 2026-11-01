# Google Forms export

**Status: the code is written, but it has not been run against a real Google account yet.** It needs an OAuth client from a Google Cloud project, which this project does not have. Until one is configured, the app says "not configured" and offers the manual export instead. No fake form link is ever shown: the link comes from Google's own response.

## What it does

1. The lecturer generates a quiz and approves every question.
2. In the quiz page they choose **Create Google Form**. The first time, they connect a Google account (Settings, Google connection).
3. The backend creates a form (`forms.create`), switches it to quiz mode and adds one multiple-choice item per approved question with its answer key and points (`forms.batchUpdate`: `updateSettings`, `createItem`).
4. The lecturer gets the form's edit link and responder link, tests the form and shares it.

Sent to Google: the quiz title and instructions, each approved question with its four options, the correct option and the marks. **Student data is never sent.** Scope requested: `https://www.googleapis.com/auth/forms.body` (create and edit forms only). The Google tokens are stored encrypted with a key derived from `SECRET_KEY`; if `SECRET_KEY` changes, lecturers reconnect.

## Set it up

1. Go to https://console.cloud.google.com, create a project, and enable the **Google Forms API**.
2. OAuth consent screen: type **External**, add your own Google account under **Test users**. Add the scope `.../auth/forms.body`.
3. Credentials, **Create credentials**, **OAuth client ID**, type **Web application**. Authorised redirect URI: `http://localhost:8000/api/integrations/google/callback` (or your server's address with the same path).
4. Put the values in `backend/.env`:

   ```
   GOOGLE_CLIENT_ID=...apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=...
   GOOGLE_REDIRECT_URI=http://localhost:8000/api/integrations/google/callback
   ```

5. Restart the backend. `/api/health` shows `"google_forms_configured": true`.

## Test it before relying on it

Connect a test account, export a small quiz, then open the form and check: it is in quiz mode, every question has four options in the right order, the answer key marks the right option, points match the marks, and a test response is scored correctly. Note anything Google does differently in `docs/ROADMAP.md`. Until this has been done, describe the integration as "implemented, not yet tested".

## Manual export (always available)

The quiz page also offers a plain-text export (questions, options and the answer key) that can be pasted into a Google Form by hand, or into any other tool.
