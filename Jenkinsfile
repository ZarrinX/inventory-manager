pipeline {
    agent any

    options {
        disableConcurrentBuilds()
        timeout(time: 30, unit: 'MINUTES')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Load Secrets') {
            steps {
                sh 'ln -sf /opt/inventory-manager/.env .env'
            }
        }

        stage('Build Image') {
            steps {
                sh 'docker compose -f docker-compose.yml build app'
            }
        }

        stage('Migrate DB') {
            steps {
                sh 'docker compose -f docker-compose.yml up -d postgres'
                sh 'docker compose -f docker-compose.yml run --rm --no-deps --entrypoint "" app alembic upgrade head'
            }
        }

        stage('Deploy App') {
            steps {
                sh 'docker compose -f docker-compose.yml up -d app --remove-orphans'
            }
        }

        stage('Cleanup') {
            steps {
                sh 'docker image prune -f'
            }
        }
    }

    post {
        failure {
            echo 'Deployment failed — previous containers are still running.'
        }
        success {
            echo 'inventory-manager deployed successfully.'
        }
    }
}
