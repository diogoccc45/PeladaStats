DROP TABLE IF EXISTS comments;
DROP TABLE IF EXISTS overall_history;
DROP TABLE IF EXISTS match_stats;
DROP TABLE IF EXISTS matches;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    nickname TEXT NOT NULL,
    preferred_foot TEXT CHECK(preferred_foot IN ('esquerdo', 'direito', 'ambidestro')),
    favorite_player_name TEXT,
    favorite_player_image_url TEXT,
    -- Ajuste de enquadramento da foto do jogador dentro do quadrado (editor em Definições).
    favorite_player_image_zoom REAL NOT NULL DEFAULT 1.0,
    favorite_player_image_pos_x REAL NOT NULL DEFAULT 50,
    favorite_player_image_pos_y REAL NOT NULL DEFAULT 50,
    favorite_team_name TEXT,
    favorite_team_logo_url TEXT,
    favorite_team_logo_zoom REAL NOT NULL DEFAULT 1.0,
    favorite_team_logo_pos_x REAL NOT NULL DEFAULT 50,
    favorite_team_logo_pos_y REAL NOT NULL DEFAULT 50,
    -- Overall persiste aqui porque é cumulativo (sobe/desce jogo a jogo);
    -- não é recalculado do zero a partir do histórico, é atualizado incrementalmente.
    overall REAL NOT NULL DEFAULT 65,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_date DATE NOT NULL,
    location TEXT,
    team_a_score INTEGER NOT NULL,
    team_b_score INTEGER NOT NULL,
    -- Pendente até a soma dos golos por jogador bater certo com o resultado e o MVP ser válido.
    status TEXT NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente', 'confirmado')),
    -- Who created this match — only they can delete it, and only while pendente.
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE match_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team TEXT NOT NULL CHECK(team IN ('A', 'B')),
    goals INTEGER NOT NULL DEFAULT 0,
    assists INTEGER NOT NULL DEFAULT 0,
    -- Em quem este jogador votou para MVP do jogo (nunca em si próprio).
    mvp_vote_for INTEGER REFERENCES users(id),
    -- Em quem este jogador votou para Golo da Jornada (nunca em si próprio;
    -- só faz sentido votar em alguém que marcou pelo menos um golo).
    goal_of_match_vote_for INTEGER REFERENCES users(id),
    -- Distingue "ainda não preencheu" de "preencheu 0 golos/assistências a sério".
    submitted INTEGER NOT NULL DEFAULT 0,
    UNIQUE(match_id, user_id),
    CHECK(mvp_vote_for IS NULL OR mvp_vote_for != user_id),
    CHECK(goal_of_match_vote_for IS NULL OR goal_of_match_vote_for != user_id)
);

-- Guarda o Overall de cada jogador após cada jogo confirmado, para o gráfico de evolução.
CREATE TABLE overall_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    match_id INTEGER REFERENCES matches(id) ON DELETE CASCADE,
    overall_after REAL NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Achievement/record unlocks queued for the player to see (confetti + toast)
-- on their next page load — created once, per player, at match confirmation
-- time (not during an admin recompute replay, to avoid flooding everyone
-- with old notifications after a correction).
-- Achievement/record unlocks (kind='unlock') and match-created reminders
-- (kind='reminder'), surfaced two ways:
--   - celebrated_at: confetti + toast shown once, right after the player's
--     next page load — only fires for kind='unlock'.
--   - seen_at: the player opened the notifications bell and read it — this
--     is what the unread badge counts, independent of the celebration.
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL DEFAULT 'unlock' CHECK(kind IN ('unlock', 'reminder')),
    label TEXT NOT NULL,
    match_id INTEGER REFERENCES matches(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    celebrated_at TIMESTAMP,
    seen_at TIMESTAMP
);
