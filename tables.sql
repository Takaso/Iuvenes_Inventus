CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    user_type VARCHAR(50) DEFAULT 'Student',
    profile_pic VARCHAR(255),
    bio TEXT,
    cv_file VARCHAR(255),
    address VARCHAR(255),
    phone VARCHAR(50)
);

CREATE TABLE tags (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE user_tags (
  user_id INT NOT NULL,
  tag_id INT NOT NULL,
  PRIMARY KEY(user_id, tag_id),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
);
