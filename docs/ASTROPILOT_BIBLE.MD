AstroPilot Bible
Version : 1.0

Préambule

Ce document constitue la référence fondatrice d'AstroPilot.
Il définit la mission, les principes, les objectifs et la philosophie qui guideront toutes les décisions d'architecture, de développement et de conception du projet.
Les algorithmes évolueront.
Les modèles physiques évolueront.
Les interfaces évolueront.
Les technologies évolueront.
En revanche, les principes décrits dans ce document ne devront évoluer qu'après une réflexion approfondie.
En cas de conflit entre une implémentation technique et les principes définis ici, ce document prévaut toujours.

Pourquoi AstroPilot existe

L'astrophotographie est une discipline où chaque session est une succession de décisions.
Avant même d'acquérir la première image, l'astrophotographe doit répondre à de nombreuses questions :
Dois-je sortir cette nuit ?
Quel objet photographier ?
Quel instrument utiliser ?
Quel filtre choisir ?
Les conditions sont-elles suffisamment bonnes ?
Est-il préférable de terminer un projet ou d'en commencer un nouveau ?
Mon matériel est-il adapté à cette cible ?
Combien de temps dois-je investir ?
Est-il préférable d'attendre une meilleure nuit ?
Aujourd'hui, la plupart des logiciels fournissent des informations.
AstroPilot existe pour transformer ces informations en décisions argumentées.
Sa vocation n'est pas uniquement d'informer l'utilisateur, mais de lui fournir un raisonnement clair, transparent et justifiable lui permettant de prendre la meilleure décision possible.

Notre mission

AstroPilot augmente les capacités décisionnelles de l'astrophotographe.
En combinant des modèles physiques, une connaissance experte et un raisonnement transparent, AstroPilot aide chaque utilisateur à prendre des décisions plus pertinentes, plus rapides et mieux justifiées.
Son objectif n'est pas de décider à la place de l'utilisateur.
Son objectif est de lui fournir les éléments nécessaires pour prendre, en toute confiance, la meilleure décision possible selon son matériel, ses projets, les conditions du ciel et ses objectifs personnels.

Notre devise

Turning astrophotography data into confident decisions.
Je pense que ce texte a une qualité importante : il ne parle ni de Python, ni d'IA, ni de technologies. Il décrit un objectif qui restera valable même si AstroPilot change complètement de langage, de plateforme ou d'architecture dans dix ans.

Les principes fondateurs

1. La décision avant l'information
AstroPilot ne présente pas uniquement des données.
Il transforme les données disponibles en recommandations argumentées.
Chaque information affichée doit contribuer à une décision.

2. Les modèles physiques avant les heuristiques
Lorsqu'un phénomène peut être expliqué par un modèle physique fiable, celui-ci est toujours privilégié.
Les heuristiques ne sont utilisées que lorsqu'aucun modèle robuste n'existe.

3. Chaque recommandation doit être explicable
Aucune recommandation ne doit être produite sans pouvoir répondre clairement aux questions suivantes :
Pourquoi cette recommandation ?
Quels facteurs ont influencé la décision ?
Quels éléments ont été défavorables ?
Quels éléments ont été favorables ?
Quelle est la confiance associée à cette recommandation ?

4. Aucun score n'est une boîte noire
Tous les scores calculés par AstroPilot doivent pouvoir être décomposés.
L'utilisateur doit pouvoir comprendre précisément comment ils sont obtenus.

5. Les décisions sont multicritères
Une bonne décision n'est jamais basée sur un seul facteur.
Chaque recommandation résulte de la combinaison de plusieurs moteurs spécialisés.

6. Les moteurs sont indépendants
Chaque moteur possède une responsabilité unique.
Il peut évoluer indépendamment des autres.
Aucun moteur ne doit contenir de logique métier appartenant à un autre moteur.

7. Le portefeuille est plus important que la nuit
AstroPilot n'optimise pas uniquement une session.
Il optimise la progression de l'ensemble du portefeuille astrophotographique.

8. La transparence prévaut toujours sur la complexité
Un algorithme très performant mais incompréhensible est moins utile qu'un algorithme légèrement moins performant mais totalement explicable.
La confiance de l'utilisateur est une priorité.

9. AstroPilot assiste l'utilisateur
AstroPilot ne remplace jamais le jugement humain.
Il fournit les éléments nécessaires pour permettre une décision éclairée.
La responsabilité finale appartient toujours à l'utilisateur.

10. Chaque nouveau moteur doit apporter une valeur décisionnelle mesurable
Aucun moteur ne sera intégré uniquement parce qu'il est techniquement intéressant.
Chaque nouveau moteur doit améliorer objectivement la qualité des recommandations produites.


Les capacités cognitives d'AstroPilot

AstroPilot est conçu comme un système expert composé de capacités cognitives indépendantes.
Chaque évolution du projet doit renforcer une ou plusieurs de ces capacités.
Les fonctionnalités ne sont qu'une conséquence de ces capacités.

1. Comprendre
AstroPilot comprend le contexte de la session.
Il analyse notamment :
les conditions météorologiques ;
la qualité du ciel ;
les caractéristiques des objets ;
le matériel disponible ;
les contraintes de temps ;
l'état d'avancement des projets.

2. Évaluer
AstroPilot est capable d'estimer objectivement les performances attendues.
Il évalue notamment :
la qualité d'image prévisible ;
les performances du setup ;
les limitations physiques ;
les risques associés à une session.

3. Comparer
AstroPilot compare plusieurs stratégies possibles.
Il peut comparer :
plusieurs objets ;
plusieurs instruments ;
plusieurs caméras ;
plusieurs filtres ;
plusieurs nuits ;
plusieurs scénarios.

4. Décider
AstroPilot transforme les analyses disponibles en recommandations argumentées.
Chaque recommandation est le résultat d'un raisonnement multicritère.

5. Expliquer
Chaque décision est accompagnée d'une explication détaillée.
Le moteur doit toujours être capable de justifier :
pourquoi une option est retenue ;
pourquoi les autres sont écartées ;
quels compromis ont été réalisés.

6. Simuler
AstroPilot répond naturellement aux questions du type :
Et si... ?
Par exemple :
Et si j'utilisais une autre caméra ?
Et si je disposais de seulement une heure ?
Et si le seeing était meilleur ?
Et si j'utilisais une autre focale ?

7. Capitaliser
AstroPilot construit progressivement une mémoire technique.
Cette mémoire comprend :
les connaissances astrophotographiques ;
les caractéristiques des objets ;
les profils du matériel ;
les retours d'expérience ;
les décisions passées.

8. Apprendre
À terme, AstroPilot devra être capable d'améliorer progressivement la qualité de ses recommandations grâce aux observations réalisées et aux retours des utilisateurs.
L'objectif n'est pas de remplacer les modèles physiques.
L'objectif est d'enrichir progressivement leur utilisation grâce à l'expérience accumulée.

Ce qu'AstroPilot ne cherche pas à être

AstroPilot ne cherche pas à remplacer les logiciels spécialisés.
Il ne cherche pas à devenir :
un logiciel d'acquisition ;
un logiciel de traitement d'images ;
un planétarium ;
un logiciel météo ;
un catalogue astronomique ;
un outil de pilotage de monture.
Ces logiciels existent déjà et excellent dans leur domaine.
AstroPilot a une mission différente.
Il transforme les informations produites par ces outils en décisions argumentées.
Son rôle est de raisonner.
Pas de remplacer les outils existants.


"Le code est un moyen. L'architecture est un multiplicateur. La confiance des utilisateurs est l'objectif."

