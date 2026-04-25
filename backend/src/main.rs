use axum::{
    extract::{Path, Query},
    http::{Request, StatusCode},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{delete, get},
    Json, Router,
};
use chrono::Utc;
use jsonwebtoken::{decode, encode, DecodingKey, EncodingKey, Header, Validation};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::path::PathBuf;
use std::process::Command;
use std::sync::Arc;
use tower_http::cors::CorsLayer;
use tower_http::services::ServeDir;
use tracing::{info, warn};

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const INVITE_CODE: &str = "FISHING_PAL_2026";
const JWT_EXPIRY_DAYS: i64 = 7;

fn jwt_secret() -> String {
    let mut hasher = Sha256::new();
    hasher.update(INVITE_CODE.as_bytes());
    hasher.update(b"::fishing-prediction-salt::2026");
    hex::encode(hasher.finalize())
}

fn project_root() -> PathBuf {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir.parent().unwrap().to_owned()
}

fn python_exe() -> String {
    // Windows venv
    let win_venv = project_root()
        .join(".venv").join("Scripts").join("python.exe");
    if win_venv.exists() {
        return win_venv.to_string_lossy().to_string();
    }
    // Linux venv
    let linux_venv = project_root()
        .join(".venv").join("bin").join("python");
    if linux_venv.exists() {
        return linux_venv.to_string_lossy().to_string();
    }
    // System fallback
    for name in &["python3", "python"] {
        if std::process::Command::new(name)
            .arg("--version")
            .output()
            .is_ok()
        {
            return name.to_string();
        }
    }
    "python3".to_string()
}

// ---------------------------------------------------------------------------
// Auth models
// ---------------------------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Claims {
    pub sub: String, // nickname
    pub exp: usize,
    pub iat: usize,
}

#[derive(Deserialize)]
pub struct RegisterRequest {
    pub nickname: String,
    pub invite_code: String,
}

#[derive(Deserialize)]
pub struct LoginRequest {
    pub nickname: String,
}

#[derive(Serialize)]
pub struct AuthResponse {
    pub success: bool,
    pub token: Option<String>,
    pub nickname: Option<String>,
    pub error: Option<String>,
}

// ---------------------------------------------------------------------------
// Spot models
// ---------------------------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct FishingSpot {
    pub id: i64,
    pub name: String,
    pub lat: f64,
    pub lon: f64,
    pub description: String,
    pub source_url: String,
    pub likes: i32,
    pub species: String,
    pub catch_result: String,
    pub added_by: String,
    pub created_at: String,
}

#[derive(Deserialize)]
pub struct CreateSpotRequest {
    pub name: String,
    pub lat: f64,
    pub lon: f64,
    pub description: Option<String>,
    pub source_url: Option<String>,
    pub likes: Option<i32>,
    pub species: Option<String>,
    pub catch_result: Option<String>,
}

// ---------------------------------------------------------------------------
// Shared state
// ---------------------------------------------------------------------------

#[derive(Clone)]
pub struct AppState {
    pub secret: String,
    pub users: Arc<tokio::sync::RwLock<HashMap<String, String>>>, // nickname -> hashed invite
    pub spots: Arc<tokio::sync::RwLock<Vec<FishingSpot>>>,
    pub spots_path: PathBuf,
}

// ---------------------------------------------------------------------------
// JWT helpers
// ---------------------------------------------------------------------------

fn create_token(nickname: &str, secret: &str) -> Result<String, jsonwebtoken::errors::Error> {
    let now = Utc::now().timestamp() as usize;
    let claims = Claims {
        sub: nickname.to_string(),
        iat: now,
        exp: now + (JWT_EXPIRY_DAYS * 86400) as usize,
    };
    encode(
        &Header::default(),
        &claims,
        &EncodingKey::from_secret(secret.as_bytes()),
    )
}

fn verify_token(token: &str, secret: &str) -> Result<Claims, jsonwebtoken::errors::Error> {
    let token_data = decode::<Claims>(
        token,
        &DecodingKey::from_secret(secret.as_bytes()),
        &Validation::default(),
    )?;
    Ok(token_data.claims)
}

// ---------------------------------------------------------------------------
// Auth middleware
// ---------------------------------------------------------------------------

async fn auth_middleware(
    axum::extract::State(state): axum::extract::State<AppState>,
    mut req: Request<axum::body::Body>,
    next: Next,
) -> Result<impl IntoResponse, (StatusCode, Json<serde_json::Value>)> {
    let secret = &state.secret;

    let auth_header = req
        .headers()
        .get("Authorization")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "));

    match auth_header {
        Some(token) => match verify_token(token, &secret) {
            Ok(claims) => {
                req.extensions_mut().insert(claims);
                Ok(next.run(req).await)
            }
            Err(_) => Err((
                StatusCode::UNAUTHORIZED,
                Json(serde_json::json!({
                    "success": false,
                    "error": "Invalid or expired token"
                })),
            )),
        },
        None => Err((
            StatusCode::UNAUTHORIZED,
            Json(serde_json::json!({
                "success": false,
                "error": "Missing Authorization header"
            })),
        )),
    }
}


// ---------------------------------------------------------------------------
// Auth routes
// ---------------------------------------------------------------------------

async fn register(
    state: axum::extract::State<AppState>,
    Json(req): Json<RegisterRequest>,
) -> Json<AuthResponse> {
    if req.nickname.trim().is_empty() {
        return Json(AuthResponse {
            success: false,
            token: None,
            nickname: None,
            error: Some("Nickname is required".to_string()),
        });
    }

    if req.invite_code != INVITE_CODE {
        return Json(AuthResponse {
            success: false,
            token: None,
            nickname: None,
            error: Some("Invalid invite code".to_string()),
        });
    }

    let nickname = req.nickname.trim().to_string();
    {
        let users = state.users.read().await;
        if users.contains_key(&nickname) {
            return Json(AuthResponse {
                success: false,
                token: None,
                nickname: None,
                error: Some("Nickname already registered".to_string()),
            });
        }
    }

    // Store user
    let hashed = hex::encode(Sha256::digest(req.invite_code.as_bytes()));
    state.users.write().await.insert(nickname.clone(), hashed);

    let token = create_token(&nickname, &state.secret).unwrap_or_default();

    info!("User registered: {}", nickname);
    Json(AuthResponse {
        success: true,
        token: Some(token),
        nickname: Some(nickname),
        error: None,
    })
}

async fn login(
    state: axum::extract::State<AppState>,
    Json(req): Json<LoginRequest>,
) -> Json<AuthResponse> {
    let nickname = req.nickname.trim().to_string();
    let users = state.users.read().await;

    if !users.contains_key(&nickname) {
        return Json(AuthResponse {
            success: false,
            token: None,
            nickname: None,
            error: Some("User not registered".to_string()),
        });
    }

    let token = create_token(&nickname, &state.secret).unwrap_or_default();

    info!("User logged in: {}", nickname);
    Json(AuthResponse {
        success: true,
        token: Some(token),
        nickname: Some(nickname),
        error: None,
    })
}

// ---------------------------------------------------------------------------
// Spot routes (protected)
// ---------------------------------------------------------------------------

async fn list_spots(
    state: axum::extract::State<AppState>,
) -> Json<serde_json::Value> {
    let spots = state.spots.read().await;
    Json(serde_json::json!({
        "success": true,
        "spots": spots.clone(),
    }))
}

async fn create_spot(
    state: axum::extract::State<AppState>,
    claims: axum::extract::Extension<Claims>,
    Json(req): Json<CreateSpotRequest>,
) -> Response {
    if req.name.trim().is_empty() {
        return (StatusCode::BAD_REQUEST, Json(serde_json::json!({
            "success": false, "error": "Name is required"
        }))).into_response();
    }

    let mut spots = state.spots.write().await;
    let new_id = spots.last().map(|s| s.id + 1).unwrap_or(1);
    let now = chrono::Utc::now().format("%Y-%m-%d %H:%M:%S").to_string();

    let spot = FishingSpot {
        id: new_id,
        name: req.name.trim().to_string(),
        lat: req.lat,
        lon: req.lon,
        description: req.description.unwrap_or_default(),
        source_url: req.source_url.unwrap_or_default(),
        likes: req.likes.unwrap_or(0),
        species: req.species.unwrap_or_default(),
        catch_result: req.catch_result.unwrap_or_default(),
        added_by: claims.0.sub.clone(),
        created_at: now,
    };

    spots.push(spot.clone());

    // Persist to file
    if let Ok(json) = serde_json::to_string_pretty(&*spots) {
        let _ = std::fs::write(&state.spots_path, &json);
    }

    (StatusCode::CREATED, Json(serde_json::json!({
        "success": true,
        "spot": spot,
    }))).into_response()
}

async fn delete_spot(
    state: axum::extract::State<AppState>,
    Path(id): Path<i64>,
) -> Json<serde_json::Value> {
    let mut spots = state.spots.write().await;
    let len = spots.len();
    spots.retain(|s| s.id != id);

    if spots.len() == len {
        return Json(serde_json::json!({
            "success": false, "error": "Spot not found"
        }));
    }

    // Persist to file
    if let Ok(json) = serde_json::to_string_pretty(&*spots) {
        let _ = std::fs::write(&state.spots_path, &json);
    }

    Json(serde_json::json!({ "success": true }))
}

// ---------------------------------------------------------------------------
// Prediction routes (protected)
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
pub struct PredictQuery {
    pub lat: f64,
    pub lon: f64,
    pub date: Option<String>,
    pub hour: Option<i32>,
}

#[derive(Deserialize)]
pub struct DayQuery {
    pub lat: f64,
    pub lon: f64,
}

async fn predict(
    claims: axum::extract::Extension<Claims>,
    query: Query<PredictQuery>,
) -> Response {
    let q = query.0;
    let date = q
        .date
        .unwrap_or_else(|| chrono::Local::now().format("%Y-%m-%d").to_string());
    let hour = q.hour.unwrap_or(6);

    info!("Predict by {}: lat={} lon={} date={} hour={}", claims.0.sub, q.lat, q.lon, date, hour);

    let script = project_root()
        .join("backend")
        .join("predict_helper.py");

    let output = Command::new(python_exe())
        .arg(&script)
        .arg(q.lat.to_string())
        .arg(q.lon.to_string())
        .arg(&date)
        .arg(hour.to_string())
        .current_dir(project_root())
        .output();

    match output {
        Ok(out) if out.status.success() => {
            let stdout = String::from_utf8_lossy(&out.stdout);
            match serde_json::from_str::<HashMap<String, serde_json::Value>>(&stdout) {
                Ok(mut data) => {
                    data.insert("success".to_string(), serde_json::Value::Bool(true));
                    data.insert(
                        "location".to_string(),
                        serde_json::json!({"lat": q.lat, "lon": q.lon}),
                    );
                    data.insert("date".to_string(), serde_json::Value::String(date));
                    data.insert("hour".to_string(), serde_json::json!(hour));
                    data.insert("user".to_string(), serde_json::Value::String(claims.0.sub.clone()));
                    (StatusCode::OK, Json(data)).into_response()
                }
                Err(e) => (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    Json(serde_json::json!({
                        "success": false,
                        "error": format!("JSON parse error: {}", e),
                    })),
                )
                    .into_response(),
            }
        }
        Ok(out) => {
            let stderr = String::from_utf8_lossy(&out.stderr);
            warn!("Prediction subprocess failed: {}", stderr);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({
                    "success": false,
                    "error": stderr.to_string(),
                })),
            )
                .into_response()
        }
        Err(e) => {
            warn!("Prediction process error: {}", e);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({
                    "success": false,
                    "error": format!("Process error: {}", e),
                })),
            )
                .into_response()
        }
    }
}

async fn predict_day(claims: axum::extract::Extension<Claims>, query: Query<DayQuery>) -> Response {
    let q = query.0;
    info!("PredictDay by {}: lat={} lon={}", claims.0.sub, q.lat, q.lon);

    let script = project_root()
        .join("backend")
        .join("predict_day_helper.py");

    let output = Command::new(python_exe())
        .arg(&script)
        .arg(q.lat.to_string())
        .arg(q.lon.to_string())
        .current_dir(project_root())
        .output();

    match output {
        Ok(out) if out.status.success() => {
            let stdout = String::from_utf8_lossy(&out.stdout);
            match serde_json::from_str::<Vec<serde_json::Value>>(&stdout) {
                Ok(hourly) => (
                    StatusCode::OK,
                    Json(serde_json::json!({
                        "success": true,
                        "hourly": hourly,
                        "location": { "lat": q.lat, "lon": q.lon },
                        "user": claims.0.sub.clone(),
                    })),
                )
                    .into_response(),
                Err(e) => (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    Json(serde_json::json!({
                        "success": false,
                        "error": format!("JSON parse error: {}", e),
                    })),
                )
                    .into_response(),
            }
        }
        Ok(out) => {
            let stderr = String::from_utf8_lossy(&out.stderr);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({
                    "success": false,
                    "error": stderr.to_string(),
                })),
            )
                .into_response()
        }
        Err(e) => {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({
                    "success": false,
                    "error": format!("Process error: {}", e),
                })),
            )
                .into_response()
        }
    }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter("info")
        .init();

    let secret = jwt_secret();
    info!("JWT secret initialized ({} bytes)", secret.len());
    info!("Invite code: {}", INVITE_CODE);

    // Load spots from file
    let spots_path = project_root().join("backend").join("spots.json");
    let spots: Vec<FishingSpot> = if spots_path.exists() {
        let content = std::fs::read_to_string(&spots_path).unwrap_or_default();
        serde_json::from_str(&content).unwrap_or_default()
    } else {
        Vec::new()
    };
    info!("Loaded {} fishing spots from {:?}", spots.len(), spots_path);

    let state = AppState {
        secret,
        users: Arc::new(tokio::sync::RwLock::new(HashMap::new())),
        spots: Arc::new(tokio::sync::RwLock::new(spots)),
        spots_path,
    };

    // Public routes (no auth needed)
    let public_routes = Router::new()
        .route("/health", get(|| async { "OK" }))
        .route("/auth/register", axum::routing::post(register))
        .route("/auth/login", axum::routing::post(login));

    // Protected routes (JWT required)
    let protected_routes = Router::new()
        .route("/predict", get(predict))
        .route("/predict/day", get(predict_day))
        .route("/api/spots", get(list_spots).post(create_spot))
        .route("/api/spots/{id}", delete(delete_spot))
        .layer(middleware::from_fn_with_state(state.clone(), auth_middleware));

    let frontend = ServeDir::new(project_root().join("backend").join("frontend"));

    let app = Router::new()
        .merge(public_routes)
        .merge(protected_routes)
        .layer(CorsLayer::permissive())
        .with_state(state)
        .fallback_service(frontend);

    let addr = "0.0.0.0:9090";
    info!("Server starting on http://{}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
