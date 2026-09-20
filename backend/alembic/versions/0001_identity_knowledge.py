# ruff: noqa: E501
"""初始化身份、权限、知识库和 RAG 生命周期表。

Revision ID: 0001_identity_knowledge
Revises:
"""

from alembic import op

revision = "0001_identity_knowledge"
down_revision = None
branch_labels = None
depends_on = None


def _execute_script(sql: str) -> None:
    """逐条执行固定迁移语句，兼容 asyncpg 的单语句预编译限制。"""
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    _execute_script(
        """
        CREATE TABLE tenants (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            code VARCHAR(64) NOT NULL UNIQUE,
            name VARCHAR(120) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE roles (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            code VARCHAR(64) NOT NULL UNIQUE,
            name VARCHAR(80) NOT NULL,
            scope VARCHAR(20) NOT NULL CHECK (scope IN ('platform','tenant','knowledge_base')),
            description TEXT NOT NULL DEFAULT '',
            is_system BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE menus (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            code VARCHAR(100) NOT NULL UNIQUE,
            name VARCHAR(80) NOT NULL,
            kind VARCHAR(20) NOT NULL CHECK (kind IN ('directory','menu','button')),
            parent_id BIGINT REFERENCES menus(id) ON DELETE SET NULL,
            route VARCHAR(200),
            icon VARCHAR(80),
            permission_code VARCHAR(120) NOT NULL UNIQUE,
            sort_order INTEGER NOT NULL DEFAULT 0,
            visible BOOLEAN NOT NULL DEFAULT true,
            status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE users (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            login VARCHAR(120) NOT NULL UNIQUE,
            display_name VARCHAR(100) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled')),
            platform_role_id BIGINT REFERENCES roles(id),
            last_login_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE tenant_members (
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
            status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, user_id)
        );
        CREATE TABLE role_menus (
            role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            menu_id BIGINT NOT NULL REFERENCES menus(id) ON DELETE CASCADE,
            PRIMARY KEY (role_id, menu_id)
        );
        CREATE TABLE sessions (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash CHAR(64) NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX sessions_user_idx ON sessions(user_id, expires_at);
        CREATE TABLE knowledge_bases (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name VARCHAR(120) NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            purpose VARCHAR(80) NOT NULL DEFAULT 'general',
            status VARCHAR(24) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','indexing','published','disabled')),
            active_release_id BIGINT,
            active_runtime_id BIGINT,
            content_epoch BIGINT NOT NULL DEFAULT 0,
            auth_epoch BIGINT NOT NULL DEFAULT 0,
            created_by BIGINT NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, name),
            UNIQUE (tenant_id, id)
        );
        CREATE TABLE kb_members (
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            knowledge_base_id BIGINT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
            status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (knowledge_base_id, user_id),
            FOREIGN KEY (tenant_id, knowledge_base_id) REFERENCES knowledge_bases(tenant_id, id)
        );
        CREATE TABLE datasets (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            knowledge_base_id BIGINT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            name VARCHAR(120) NOT NULL,
            is_default BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (knowledge_base_id, name)
        );
        CREATE TABLE documents (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            knowledge_base_id BIGINT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            dataset_id BIGINT NOT NULL REFERENCES datasets(id) ON DELETE RESTRICT,
            title VARCHAR(240) NOT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled','deleted')),
            desired_version_id BIGINT,
            deleted_at TIMESTAMPTZ,
            created_by BIGINT NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, id)
        );
        CREATE TABLE document_versions (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            version_no INTEGER NOT NULL,
            storage_key VARCHAR(500) NOT NULL,
            sha256 CHAR(64) NOT NULL,
            mime_type VARCHAR(120) NOT NULL,
            file_size BIGINT NOT NULL CHECK (file_size >= 0),
            parse_status VARCHAR(24) NOT NULL DEFAULT 'queued' CHECK (parse_status IN ('queued','processing','complete','partial','unsupported','failed')),
            warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_by BIGINT NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (document_id, version_no),
            UNIQUE (tenant_id, id)
        );
        ALTER TABLE documents ADD CONSTRAINT documents_desired_version_fk FOREIGN KEY (desired_version_id) REFERENCES document_versions(id);
        CREATE TABLE model_endpoints (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT REFERENCES tenants(id) ON DELETE CASCADE,
            name VARCHAR(120) NOT NULL,
            provider VARCHAR(40) NOT NULL,
            endpoint_type VARCHAR(30) NOT NULL CHECK (endpoint_type IN ('generation','embedding','reranker')),
            base_url VARCHAR(300) NOT NULL,
            secret_ref VARCHAR(200),
            allowed_models JSONB NOT NULL DEFAULT '[]'::jsonb,
            health_status VARCHAR(24) NOT NULL DEFAULT 'unknown',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE ingestion_profiles (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            knowledge_base_id BIGINT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            definition JSONB NOT NULL,
            definition_hash CHAR(64) NOT NULL,
            created_by BIGINT NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (knowledge_base_id, definition_hash)
        );
        CREATE TABLE embedding_profiles (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            model_endpoint_id BIGINT NOT NULL REFERENCES model_endpoints(id) ON DELETE RESTRICT,
            model_name VARCHAR(160) NOT NULL,
            model_revision VARCHAR(240) NOT NULL,
            dimension INTEGER NOT NULL CHECK (dimension > 0),
            dtype VARCHAR(20) NOT NULL,
            instructions JSONB NOT NULL DEFAULT '{}'::jsonb,
            normalization VARCHAR(30) NOT NULL,
            definition_hash CHAR(64) NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE runtime_profiles (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            knowledge_base_id BIGINT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            embedding_profile_id BIGINT NOT NULL REFERENCES embedding_profiles(id) ON DELETE RESTRICT,
            definition JSONB NOT NULL,
            definition_hash CHAR(64) NOT NULL,
            created_by BIGINT NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (knowledge_base_id, definition_hash)
        );
        CREATE TABLE index_builds (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            knowledge_base_id BIGINT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            base_release_id BIGINT,
            input_epoch BIGINT NOT NULL,
            ingestion_profile_id BIGINT NOT NULL REFERENCES ingestion_profiles(id),
            embedding_profile_id BIGINT NOT NULL REFERENCES embedding_profiles(id),
            state VARCHAR(24) NOT NULL DEFAULT 'queued' CHECK (state IN ('queued','running','validating','ready','failed','cancelled')),
            error JSONB,
            created_by BIGINT NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE document_artifacts (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            knowledge_base_id BIGINT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            document_version_id BIGINT NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
            ingestion_profile_id BIGINT NOT NULL REFERENCES ingestion_profiles(id),
            state VARCHAR(24) NOT NULL DEFAULT 'processing' CHECK (state IN ('processing','ready','partial','failed')),
            manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (document_version_id, ingestion_profile_id)
        );
        CREATE TABLE chunks (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            knowledge_base_id BIGINT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            artifact_id BIGINT NOT NULL REFERENCES document_artifacts(id) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL,
            content TEXT NOT NULL,
            embed_text TEXT NOT NULL,
            token_count INTEGER NOT NULL CHECK (token_count > 0),
            section_path JSONB NOT NULL DEFAULT '[]'::jsonb,
            locator JSONB NOT NULL,
            lexical_tsv TSVECTOR,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (artifact_id, ordinal)
        );
        CREATE INDEX chunks_lexical_idx ON chunks USING gin(lexical_tsv);
        CREATE TABLE chunk_embeddings (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            knowledge_base_id BIGINT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            chunk_id BIGINT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
            embedding_profile_id BIGINT NOT NULL REFERENCES embedding_profiles(id) ON DELETE RESTRICT,
            embedding vector(1024) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (chunk_id, embedding_profile_id)
        );
        CREATE TABLE kb_releases (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            knowledge_base_id BIGINT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            build_id BIGINT NOT NULL REFERENCES index_builds(id) ON DELETE RESTRICT,
            embedding_profile_id BIGINT NOT NULL REFERENCES embedding_profiles(id),
            manifest_hash CHAR(64) NOT NULL,
            state VARCHAR(24) NOT NULL DEFAULT 'ready' CHECK (state IN ('ready','retired','invalidated')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (knowledge_base_id, manifest_hash)
        );
        ALTER TABLE knowledge_bases ADD CONSTRAINT knowledge_bases_active_release_fk FOREIGN KEY (active_release_id) REFERENCES kb_releases(id);
        ALTER TABLE knowledge_bases ADD CONSTRAINT knowledge_bases_active_runtime_fk FOREIGN KEY (active_runtime_id) REFERENCES runtime_profiles(id);
        ALTER TABLE index_builds ADD CONSTRAINT index_builds_base_release_fk FOREIGN KEY (base_release_id) REFERENCES kb_releases(id);
        CREATE TABLE release_items (
            release_id BIGINT NOT NULL REFERENCES kb_releases(id) ON DELETE CASCADE,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            knowledge_base_id BIGINT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
            document_version_id BIGINT NOT NULL REFERENCES document_versions(id) ON DELETE RESTRICT,
            artifact_id BIGINT NOT NULL REFERENCES document_artifacts(id) ON DELETE RESTRICT,
            PRIMARY KEY (release_id, document_id)
        );
        CREATE TABLE tasks (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            knowledge_base_id BIGINT REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            task_type VARCHAR(40) NOT NULL,
            state VARCHAR(24) NOT NULL DEFAULT 'queued' CHECK (state IN ('queued','running','completed','failed','cancelled','interrupted')),
            idempotency_key VARCHAR(180) NOT NULL,
            attempt INTEGER NOT NULL DEFAULT 0,
            lease_until TIMESTAMPTZ,
            fencing_token BIGINT NOT NULL DEFAULT 0,
            error JSONB,
            created_by BIGINT REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, idempotency_key)
        );
        CREATE TABLE task_items (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            target_id BIGINT,
            stage VARCHAR(40) NOT NULL,
            state VARCHAR(24) NOT NULL DEFAULT 'queued',
            attempt INTEGER NOT NULL DEFAULT 0,
            error JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE outbox_events (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            event_type VARCHAR(80) NOT NULL,
            payload JSONB NOT NULL,
            state VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','sent','failed')),
            next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            attempt INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE conversations (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            knowledge_base_id BIGINT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            owner_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title VARCHAR(200) NOT NULL DEFAULT '新会话',
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE messages (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL CHECK (role IN ('user','assistant','system')),
            content TEXT NOT NULL DEFAULT '',
            state VARCHAR(24) NOT NULL DEFAULT 'pending',
            request_id UUID,
            release_id BIGINT REFERENCES kb_releases(id),
            runtime_id BIGINT REFERENCES runtime_profiles(id),
            usage JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (conversation_id, request_id)
        );
        CREATE TABLE message_citations (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            message_id BIGINT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            chunk_id BIGINT NOT NULL REFERENCES chunks(id) ON DELETE RESTRICT,
            document_version_id BIGINT NOT NULL REFERENCES document_versions(id) ON DELETE RESTRICT,
            evidence_no INTEGER NOT NULL,
            locator JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (message_id, evidence_no)
        );
        CREATE TABLE message_evidence (
            message_id BIGINT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
            document_version_id BIGINT NOT NULL REFERENCES document_versions(id) ON DELETE RESTRICT,
            PRIMARY KEY (message_id, document_id, document_version_id)
        );
        CREATE TABLE retrieval_traces (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            knowledge_base_id BIGINT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            message_id BIGINT REFERENCES messages(id) ON DELETE SET NULL,
            query TEXT NOT NULL,
            rewritten_query TEXT,
            profiles JSONB NOT NULL,
            timings JSONB NOT NULL DEFAULT '{}'::jsonb,
            state VARCHAR(24) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE retrieval_trace_items (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            trace_id BIGINT NOT NULL REFERENCES retrieval_traces(id) ON DELETE CASCADE,
            chunk_id BIGINT NOT NULL REFERENCES chunks(id) ON DELETE RESTRICT,
            route VARCHAR(24) NOT NULL,
            rank INTEGER,
            score DOUBLE PRECISION,
            fused_rank INTEGER,
            rerank_score DOUBLE PRECISION,
            in_context BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE feedback (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            message_id BIGINT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            rating VARCHAR(20) NOT NULL CHECK (rating IN ('helpful','not_helpful')),
            reason VARCHAR(200),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (message_id, user_id)
        );
        CREATE TABLE audit_logs (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT REFERENCES tenants(id) ON DELETE SET NULL,
            actor_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
            action VARCHAR(100) NOT NULL,
            target_type VARCHAR(80) NOT NULL,
            target_id VARCHAR(120),
            change_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
            request_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX tenant_members_user_idx ON tenant_members(user_id, status);
        CREATE INDEX kb_members_user_idx ON kb_members(user_id, status);
        CREATE INDEX documents_kb_idx ON documents(tenant_id, knowledge_base_id, status, updated_at DESC);
        CREATE INDEX tasks_state_idx ON tasks(tenant_id, state, updated_at);
        CREATE INDEX audit_logs_tenant_idx ON audit_logs(tenant_id, created_at DESC);
        """
    )
    _seed_roles_and_menus()
    _comment_schema()


def _seed_roles_and_menus() -> None:
    _execute_script(
        """
        INSERT INTO roles(code,name,scope,description,is_system) VALUES
        ('platform_admin','平台管理员','platform','管理客户空间、账号、模型和系统配置',true),
        ('space_admin','空间管理员','tenant','管理客户空间成员和空间内知识库',true),
        ('space_member','空间成员','tenant','已加入空间但仅能访问显式授权的知识库',true),
        ('kb_admin','知识库管理员','knowledge_base','管理知识库内容、发布和检索调试',true),
        ('editor','编辑者','knowledge_base','上传资料并处理失败任务，不能发布',true),
        ('reader','读者','knowledge_base','查看已发布资料、问答和引用',true),
        ('customer_reader','客户用户','tenant','客户空间内只读问答用户',true)
        ON CONFLICT (code) DO NOTHING;
        INSERT INTO menus(code,name,kind,route,icon,permission_code,sort_order) VALUES
        ('dashboard','工作台','menu','/dashboard','LayoutDashboard','dashboard:view',10),
        ('knowledge','知识库管理','directory',NULL,'Library','knowledge:view',20),
        ('knowledge-bases','知识库列表','menu','/knowledge-bases','Library','knowledge_base:list',21),
        ('documents','文档管理','menu','/documents','Files','document:list',22),
        ('releases','发布版本','menu','/releases','GitBranch','release:list',23),
        ('chat','知识问答','menu','/chat','MessageSquare','chat:use',30),
        ('retrieval','检索与评测','directory',NULL,'SearchCheck','retrieval:view',40),
        ('search-test','检索调试','menu','/search-test','Search','retrieval:test',41),
        ('tasks','任务中心','menu','/tasks','ListTodo','task:list',50),
        ('customers','客户空间','directory',NULL,'Building2','space:view',60),
        ('members','空间成员','menu','/members','Users','member:list',61),
        ('system','系统管理','directory',NULL,'Settings2','system:view',70),
        ('users','用户管理','menu','/system/users','UserRound','user:list',71),
        ('roles','角色管理','menu','/system/roles','ShieldCheck','role:list',72),
        ('menus','菜单管理','menu','/system/menus','Menu','menu:list',73),
        ('audit','操作日志','menu','/system/audit','ScrollText','audit:list',74),
        ('models','模型服务','menu','/system/models','Cpu','model:list',80)
        ON CONFLICT (code) DO NOTHING;
        UPDATE menus child SET parent_id = parent.id
        FROM menus parent
        WHERE child.code IN ('knowledge-bases','documents','releases') AND parent.code='knowledge';
        UPDATE menus child SET parent_id = parent.id
        FROM menus parent
        WHERE child.code='search-test' AND parent.code='retrieval';
        UPDATE menus child SET parent_id = parent.id
        FROM menus parent
        WHERE child.code='members' AND parent.code='customers';
        UPDATE menus child SET parent_id = parent.id
        FROM menus parent
        WHERE child.code IN ('users','roles','menus','audit') AND parent.code='system';
        INSERT INTO role_menus(role_id,menu_id)
        SELECT r.id,m.id FROM roles r CROSS JOIN menus m WHERE r.code='platform_admin'
        ON CONFLICT DO NOTHING;
        INSERT INTO role_menus(role_id,menu_id)
        SELECT r.id,m.id FROM roles r JOIN menus m ON m.permission_code IN
        ('dashboard:view','knowledge:view','knowledge_base:list','document:list','release:list','chat:use','retrieval:view','retrieval:test','task:list','space:view','member:list','model:list')
        WHERE r.code IN ('space_admin','kb_admin') ON CONFLICT DO NOTHING;
        INSERT INTO role_menus(role_id,menu_id)
        SELECT r.id,m.id FROM roles r JOIN menus m ON m.permission_code IN
        ('dashboard:view','knowledge:view','knowledge_base:list','document:list','chat:use','task:list')
        WHERE r.code='editor' ON CONFLICT DO NOTHING;
        INSERT INTO role_menus(role_id,menu_id)
        SELECT r.id,m.id FROM roles r JOIN menus m ON m.permission_code IN
        ('dashboard:view')
        WHERE r.code='space_member' ON CONFLICT DO NOTHING;
        INSERT INTO role_menus(role_id,menu_id)
        SELECT r.id,m.id FROM roles r JOIN menus m ON m.permission_code IN
        ('dashboard:view','knowledge_base:list','chat:use')
        WHERE r.code IN ('reader','customer_reader') ON CONFLICT DO NOTHING;
        """
    )


def _comment_schema() -> None:
    table_comments = {
        "tenants": "客户空间租户；每家客户拥有独立的数据隔离边界。",
        "roles": "系统角色定义；角色通过菜单权限和空间成员关系授权。",
        "menus": "后台菜单、目录和按钮权限项定义。",
        "users": "平台登录用户；密码只保存 Argon2id 哈希。",
        "tenant_members": "用户与客户空间的成员关系及空间角色。",
        "role_menus": "角色与菜单/按钮权限的关联表。",
        "sessions": "服务端登录会话；只保存随机令牌哈希。",
        "knowledge_bases": "客户空间内的知识库及当前发布/运行指针。",
        "kb_members": "用户与知识库的成员关系及内容操作角色。",
        "datasets": "知识库数据集；首版每个知识库创建一个默认数据集。",
        "documents": "文档逻辑身份；更新通过新增文档版本完成。",
        "document_versions": "不可变的原文件版本和解析状态。",
        "model_endpoints": "受白名单约束的生成、嵌入或重排模型服务端点。",
        "ingestion_profiles": "解析、切片和词法处理规则的不可变快照。",
        "embedding_profiles": "嵌入模型、维度、指令、归一化和版本的不可变快照。",
        "runtime_profiles": "检索、重排、生成和提示词运行配置快照。",
        "index_builds": "以内容 epoch 和 profile 为快照的索引构建。",
        "document_artifacts": "文档版本经解析切片后形成的不可变处理产物。",
        "chunks": "带原文定位的检索切片正文和词法字段。",
        "chunk_embeddings": "切片在指定嵌入 profile 下生成的向量。",
        "kb_releases": "可供问答使用的知识库内容发布快照。",
        "release_items": "发布快照中的文档版本和处理产物清单。",
        "tasks": "可恢复、可幂等的后台任务主记录。",
        "task_items": "任务的逐项处理状态和失败信息。",
        "outbox_events": "与业务事务同提交、用于可靠派发后台任务的事件。",
        "conversations": "用户在单一知识库内的问答会话。",
        "messages": "会话消息和实际使用的发布/运行版本。",
        "message_citations": "回答展示的编号引用及原文定位。",
        "message_evidence": "回答上下文使用过的全部来源，用于撤权后重新授权。",
        "retrieval_traces": "检索请求的配置、查询和阶段耗时追踪。",
        "retrieval_trace_items": "检索候选的召回路由、排名和分数明细。",
        "feedback": "用户对可见回答的反馈。",
        "audit_logs": "登录、授权、内容和配置变更审计记录。",
    }
    for table, comment in table_comments.items():
        op.execute(f"COMMENT ON TABLE {table} IS '{comment}'")

    column_comments = {
        "tenants": {
            "code": "租户唯一编码",
            "name": "客户空间名称",
            "status": "空间状态：active 启用，disabled 停用",
        },
        "roles": {
            "code": "角色唯一标识",
            "name": "角色显示名称",
            "scope": "角色作用域：platform 平台、tenant 空间、knowledge_base 知识库",
            "description": "角色职责说明",
            "is_system": "是否为系统内置角色",
        },
        "menus": {
            "code": "菜单唯一编码",
            "name": "菜单或按钮名称",
            "kind": "类型：directory 目录、menu 页面、button 操作",
            "parent_id": "父级目录 ID",
            "route": "前端路由；按钮为空",
            "icon": "图标名称",
            "permission_code": "后端权限标识",
            "sort_order": "同级排序号",
            "visible": "是否在导航中显示",
            "status": "菜单状态",
        },
        "users": {
            "login": "登录名",
            "display_name": "用户显示名称",
            "password_hash": "Argon2id 密码哈希",
            "status": "账号状态",
            "platform_role_id": "平台级角色 ID",
            "last_login_at": "最近登录时间",
        },
        "tenant_members": {
            "tenant_id": "客户空间 ID",
            "user_id": "用户 ID",
            "role_id": "空间角色 ID",
            "status": "成员状态",
        },
        "sessions": {
            "user_id": "会话所属用户",
            "token_hash": "随机会话令牌的 SHA-256 哈希",
            "expires_at": "会话过期时间",
            "revoked_at": "撤销时间",
            "last_seen_at": "最近使用时间",
        },
        "knowledge_bases": {
            "tenant_id": "所属客户空间",
            "name": "知识库名称",
            "description": "知识库说明",
            "purpose": "业务用途，如技术、产品、故障或规则",
            "status": "状态：draft/indexing/published/disabled",
            "active_release_id": "当前生效的发布快照",
            "active_runtime_id": "当前生效的运行配置",
            "content_epoch": "内容变更世代，用于阻止过期发布",
            "auth_epoch": "授权变更世代",
            "created_by": "创建人",
        },
        "kb_members": {
            "tenant_id": "所属客户空间",
            "knowledge_base_id": "知识库 ID",
            "user_id": "用户 ID",
            "role_id": "知识库角色 ID",
            "status": "成员状态",
        },
        "datasets": {
            "tenant_id": "所属客户空间",
            "knowledge_base_id": "知识库 ID",
            "name": "数据集名称",
            "is_default": "是否为默认数据集",
        },
        "documents": {
            "tenant_id": "所属客户空间",
            "knowledge_base_id": "知识库 ID",
            "dataset_id": "数据集 ID",
            "title": "文档标题",
            "status": "文档状态：active/disabled/deleted",
            "desired_version_id": "编辑意图指向的最新版本",
            "deleted_at": "逻辑删除时间",
            "created_by": "上传人",
        },
        "document_versions": {
            "tenant_id": "所属客户空间",
            "document_id": "文档逻辑 ID",
            "version_no": "文档版本号",
            "storage_key": "受保护文件存储键",
            "sha256": "原文件 SHA-256",
            "mime_type": "服务端确认的 MIME 类型",
            "file_size": "原文件字节数",
            "parse_status": "解析状态",
            "warnings": "解析告警列表",
            "created_by": "上传人",
        },
        "model_endpoints": {
            "tenant_id": "所属空间；平台端点为空",
            "name": "端点名称",
            "provider": "服务提供方",
            "endpoint_type": "模型用途",
            "base_url": "内网服务地址",
            "secret_ref": "密钥引用，不保存明文",
            "allowed_models": "允许调用的模型白名单",
            "health_status": "最近健康状态",
        },
        "ingestion_profiles": {
            "tenant_id": "所属客户空间",
            "knowledge_base_id": "知识库 ID",
            "definition": "解析、切片和词法配置 JSON",
            "definition_hash": "配置内容哈希",
            "created_by": "创建人",
        },
        "embedding_profiles": {
            "model_endpoint_id": "模型端点 ID",
            "model_name": "模型服务标识",
            "model_revision": "模型 revision 或 digest",
            "dimension": "向量维度",
            "dtype": "向量数据类型",
            "instructions": "query/doc 编码指令",
            "normalization": "归一化规则",
            "definition_hash": "完整 profile 哈希",
        },
        "runtime_profiles": {
            "tenant_id": "所属客户空间",
            "knowledge_base_id": "知识库 ID",
            "embedding_profile_id": "嵌入 profile ID",
            "definition": "检索、重排、生成配置 JSON",
            "definition_hash": "配置内容哈希",
            "created_by": "创建人",
        },
        "index_builds": {
            "tenant_id": "所属客户空间",
            "knowledge_base_id": "知识库 ID",
            "base_release_id": "构建开始时的基础发布",
            "input_epoch": "构建读取的内容世代",
            "ingestion_profile_id": "处理 profile ID",
            "embedding_profile_id": "嵌入 profile ID",
            "state": "构建状态",
            "error": "失败原因 JSON",
            "created_by": "发起人",
        },
        "document_artifacts": {
            "tenant_id": "所属客户空间",
            "knowledge_base_id": "知识库 ID",
            "document_version_id": "文档版本 ID",
            "ingestion_profile_id": "处理 profile ID",
            "state": "产物状态",
            "manifest": "产物清单和统计",
        },
        "chunks": {
            "tenant_id": "所属客户空间",
            "knowledge_base_id": "知识库 ID",
            "artifact_id": "处理产物 ID",
            "ordinal": "切片在文档中的顺序",
            "content": "展示和引用的原文内容",
            "embed_text": "实际发送给嵌入模型的文本",
            "token_count": "嵌入输入 token 数",
            "section_path": "标题层级路径",
            "locator": "页码、行号或段落定位",
            "lexical_tsv": "词法检索字段",
        },
        "chunk_embeddings": {
            "tenant_id": "所属客户空间",
            "knowledge_base_id": "知识库 ID",
            "chunk_id": "切片 ID",
            "embedding_profile_id": "嵌入 profile ID",
            "embedding": "固定 1024 维向量",
        },
        "kb_releases": {
            "tenant_id": "所属客户空间",
            "knowledge_base_id": "知识库 ID",
            "build_id": "生成该发布的构建",
            "embedding_profile_id": "发布使用的嵌入 profile",
            "manifest_hash": "发布清单哈希",
            "state": "发布状态",
        },
        "release_items": {
            "release_id": "发布快照 ID",
            "tenant_id": "所属客户空间",
            "knowledge_base_id": "知识库 ID",
            "document_id": "文档逻辑 ID",
            "document_version_id": "纳入发布的文档版本",
            "artifact_id": "纳入发布的处理产物",
        },
        "tasks": {
            "tenant_id": "所属客户空间",
            "knowledge_base_id": "知识库 ID",
            "task_type": "任务类型",
            "state": "任务状态",
            "idempotency_key": "幂等键",
            "attempt": "已尝试次数",
            "lease_until": "worker 租约到期时间",
            "fencing_token": "防旧 worker 覆盖的令牌",
            "error": "错误详情 JSON",
            "created_by": "发起人",
        },
        "task_items": {
            "task_id": "任务 ID",
            "target_id": "处理目标 ID",
            "stage": "处理阶段",
            "state": "条目状态",
            "attempt": "条目重试次数",
            "error": "条目错误详情",
        },
        "outbox_events": {
            "tenant_id": "所属客户空间",
            "event_type": "事件类型",
            "payload": "事件内容",
            "state": "派发状态",
            "next_attempt_at": "下一次派发时间",
            "attempt": "派发尝试次数",
        },
        "conversations": {
            "tenant_id": "所属客户空间",
            "knowledge_base_id": "知识库 ID",
            "owner_user_id": "会话所有者",
            "title": "会话标题",
            "status": "会话状态",
        },
        "messages": {
            "tenant_id": "所属客户空间",
            "conversation_id": "会话 ID",
            "role": "消息角色",
            "content": "消息正文",
            "state": "消息状态",
            "request_id": "客户端请求幂等 ID",
            "release_id": "回答使用的发布快照",
            "runtime_id": "回答使用的运行配置",
            "usage": "模型 token 使用量",
        },
        "message_citations": {
            "message_id": "回答消息 ID",
            "chunk_id": "引用切片 ID",
            "document_version_id": "引用来源版本",
            "evidence_no": "回答中的引用编号",
            "locator": "原文定位",
        },
        "message_evidence": {
            "message_id": "回答消息 ID",
            "document_id": "来源文档 ID",
            "document_version_id": "来源文档版本",
        },
        "retrieval_traces": {
            "tenant_id": "所属客户空间",
            "knowledge_base_id": "知识库 ID",
            "user_id": "请求用户",
            "message_id": "关联回答消息",
            "query": "原始问题",
            "rewritten_query": "有限改写后的问题",
            "profiles": "实际使用的 profile",
            "timings": "各阶段耗时",
            "state": "追踪状态",
        },
        "retrieval_trace_items": {
            "tenant_id": "所属客户空间",
            "trace_id": "追踪记录 ID",
            "chunk_id": "候选切片 ID",
            "route": "召回路由：vector/lexical/fused/rerank",
            "rank": "路由内排名",
            "score": "路由分数",
            "fused_rank": "融合排名",
            "rerank_score": "重排分数",
            "in_context": "是否进入生成上下文",
        },
        "feedback": {
            "tenant_id": "所属客户空间",
            "message_id": "被评价消息",
            "user_id": "评价用户",
            "rating": "评价：helpful/not_helpful",
            "reason": "可选原因",
        },
        "audit_logs": {
            "tenant_id": "所属客户空间",
            "actor_id": "操作人",
            "action": "操作动作",
            "target_type": "目标类型",
            "target_id": "目标 ID",
            "change_summary": "变更摘要，不写密码和密钥",
            "request_id": "请求 ID",
        },
    }
    for table, columns in column_comments.items():
        for column, comment in columns.items():
            op.execute(f"COMMENT ON COLUMN {table}.{column} IS '{comment}'")


def downgrade() -> None:
    _execute_script(
        """
        DROP TABLE IF EXISTS audit_logs, feedback, retrieval_trace_items, retrieval_traces,
        message_evidence, message_citations, messages, conversations, outbox_events,
        task_items, tasks, release_items, kb_releases, chunk_embeddings, chunks,
        document_artifacts, index_builds, runtime_profiles, embedding_profiles,
        ingestion_profiles, model_endpoints, document_versions, documents, datasets,
        kb_members, knowledge_bases, sessions, role_menus, tenant_members, users, menus,
        roles, tenants CASCADE;
        """
    )
