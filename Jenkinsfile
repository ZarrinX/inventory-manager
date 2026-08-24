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

        stage('Build & Deploy') {
            steps {
                sh 'docker compose -f docker-compose.yml up --build -d --remove-orphans'
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
