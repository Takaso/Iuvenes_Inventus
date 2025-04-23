-- CV per studenti
ALTER TABLE users ADD COLUMN cv_file VARCHAR(255) NULL AFTER bio;
-- Richieste per aziende
ALTER TABLE users ADD COLUMN address VARCHAR(255) NULL AFTER cv_file;
ALTER TABLE users ADD COLUMN phone VARCHAR(50) NULL AFTER address;

-- Tabella per i tag (riutilizzabile)
CREATE TABLE tags (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(50) UNIQUE NOT NULL
);

-- Mappatura utente ↔ tag
CREATE TABLE user_tags (
  user_id INT NOT NULL,
  tag_id INT NOT NULL,
  PRIMARY KEY(user_id, tag_id),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
);