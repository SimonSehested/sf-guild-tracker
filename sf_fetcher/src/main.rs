use dotenvy::dotenv;
use serde::Serialize;
// Bemærk: "command" og ikke "commands"
use sf_api::{command::Command, SimpleSession};
use std::env;

#[derive(Serialize)]
struct MemberLevel {
    name: String,
    level: u16,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Indlæs .env fra mappen
    dotenv().ok();

    // Du logger ALTID ind med SF account (email + password)
    let username = env::var("SF_USERNAME")
        .expect("SF_USERNAME mangler (din S&F account e-mail)");
    let password = env::var("SF_PASSWORD")
        .expect("SF_PASSWORD mangler (dit S&F account password)");

    // 1) Log ind på S&F Account (SSO)
    let sessions = SimpleSession::login_sf_account(&username, &password).await?;

    // 2) Brug den første karakter på kontoen (nu mutable)
    let mut session = sessions
        .into_iter()
        .next()
        .ok_or("Ingen karakterer fundet på denne S&F account")?;

    // 3) Send et Update-command for at få frisk GameState
    let gs = session.send_command(Command::Update).await?;

    // 4) Sørg for at karakteren er i et guild
    let guild = gs
        .guild
        .as_ref()
        .ok_or("Din karakter er ikke i et guild")?;

    // 5) Saml navn + level på alle medlemmer
    let members: Vec<MemberLevel> = guild
        .members
        .iter()
        .map(|m| MemberLevel {
            name: m.name.clone(),
            level: m.level,
        })
        .collect();

    // 6) Print JSON til stdout (det læser Python-scriptet senere)
    let json = serde_json::to_string_pretty(&members)?;
    println!("{json}");

    Ok(())
}
