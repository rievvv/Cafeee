// Ganti dengan config project Firebase kamu (Project settings > Your apps > Web)
firebase.initializeApp({
  apiKey: "ISI_API_KEY",
  authDomain: "ISI_PROJECT.firebaseapp.com",
  projectId: "ISI_PROJECT_ID",
  appId: "ISI_APP_ID"
});
const db = firebase.firestore(), auth = firebase.auth();
