import AuthenticationServices
import UIKit

/// Sign in with Apple on ASAuthorizationController, the revocation notification, the name formatter and the
/// `PxAppleAuthenticationButton` view. Errors reply as "ERR_CODE: message" for the Python side.
final class AppleAuthenticationModule: PxViewModule {
    static let moduleName = "AppleAuthentication"
    static let viewTypes = ["PxAppleAuthenticationButton"]

    private var pending: Request?
    private var revokeObserver: NSObjectProtocol?

    required init() {}

    deinit {
        if let o = revokeObserver { NotificationCenter.default.removeObserver(o) }
    }

    func makeView(_ ctx: PxModuleContext, _ type: String, _ emit: @escaping (String, Any?) -> Void) -> PxNativeView {
        PxAppleAuthenticationButton(emit)
    }

    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply) {
        switch method {
        case "isAvailable": reply(true, nil)
        case "signIn": signIn(ctx, (args.first as? [String: Any]) ?? [:], reply)
        case "credentialState":
            guard let user = args.first as? String else { reply(nil, "ERR_REQUEST_FAILED: no user"); return }
            ASAuthorizationAppleIDProvider().getCredentialState(forUserID: user) { state, error in
                if let e = error { reply(nil, "ERR_REQUEST_FAILED: \(e.localizedDescription)"); return }
                switch state {
                case .revoked: reply(0, nil)
                case .authorized: reply(1, nil)
                case .transferred: reply(3, nil)
                default: reply(2, nil)
                }
            }
        case "observeRevocations":
            if revokeObserver == nil {
                revokeObserver = NotificationCenter.default.addObserver(
                    forName: ASAuthorizationAppleIDProvider.credentialRevokedNotification, object: nil, queue: .main
                ) { _ in ctx.emit("AppleAuthentication.revoked", [:]) }
            }
            reply(true, nil)
        case "formatFullName":
            reply(formatFullName((args.first as? [String: Any]) ?? [:], (args.dropFirst().first as? Int) ?? 0), nil)
        default: reply(nil, "unknown native call AppleAuthentication.\(method)")
        }
    }

    private func formatFullName(_ parts: [String: Any], _ style: Int) -> String {
        var n = PersonNameComponents()
        n.namePrefix = parts["namePrefix"] as? String
        n.givenName = parts["givenName"] as? String
        n.middleName = parts["middleName"] as? String
        n.familyName = parts["familyName"] as? String
        n.nameSuffix = parts["nameSuffix"] as? String
        n.nickname = parts["nickname"] as? String
        let f = PersonNameComponentsFormatter()
        f.style = PersonNameComponentsFormatter.Style(rawValue: style) ?? .default
        return f.string(from: n)
    }

    private func signIn(_ ctx: PxModuleContext, _ o: [String: Any], _ reply: @escaping PxReply) {
        guard pending == nil else { reply(nil, "ERR_IN_PROGRESS: a sign-in is already in progress"); return }
        guard let window = ctx.presenter()?.view.window else {
            reply(nil, "ERR_REQUEST_FAILED: no window to present from"); return
        }
        let request = ASAuthorizationAppleIDProvider().createRequest()
        var scopes: [ASAuthorization.Scope] = []
        for s in (o["scopes"] as? [Int]) ?? [] { scopes.append(s == 0 ? .fullName : .email) }
        request.requestedScopes = scopes
        switch (o["operation"] as? Int) ?? 1 {
        case 0: request.requestedOperation = .operationImplicit
        case 2: request.requestedOperation = .operationRefresh
        case 3: request.requestedOperation = .operationLogout
        default: request.requestedOperation = .operationLogin
        }
        if let user = o["user"] as? String, !user.isEmpty { request.user = user }
        if let state = o["state"] as? String, !state.isEmpty { request.state = state }
        if let nonce = o["nonce"] as? String, !nonce.isEmpty { request.nonce = nonce }
        let r = Request(window: window) { [weak self] result, error in
            self?.pending = nil
            reply(result, error)
        }
        pending = r
        let controller = ASAuthorizationController(authorizationRequests: [request])
        controller.delegate = r
        controller.presentationContextProvider = r
        r.controller = controller
        controller.performRequests()
    }
}

private final class Request: NSObject, ASAuthorizationControllerDelegate,
    ASAuthorizationControllerPresentationContextProviding {
    let window: UIWindow
    let done: (Any?, String?) -> Void
    var controller: ASAuthorizationController?

    init(window: UIWindow, done: @escaping (Any?, String?) -> Void) {
        self.window = window
        self.done = done
    }

    func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor { window }

    func authorizationController(controller: ASAuthorizationController,
                                 didCompleteWithAuthorization authorization: ASAuthorization) {
        guard let c = authorization.credential as? ASAuthorizationAppleIDCredential else {
            done(nil, "ERR_INVALID_RESPONSE: not an Apple ID credential"); return
        }
        // Helpers keep each value typed as Any; inline `String? ?? NSNull()` in a
        // dictionary literal makes the Swift type checker time out.
        func opt(_ s: String?) -> Any { s ?? NSNull() }
        func text(_ d: Data?) -> Any { opt(d.flatMap { String(data: $0, encoding: .utf8) }) }
        var name: Any = NSNull()
        if let n = c.fullName {
            let parts: [String: Any] = [
                "namePrefix": opt(n.namePrefix), "givenName": opt(n.givenName),
                "middleName": opt(n.middleName), "familyName": opt(n.familyName),
                "nameSuffix": opt(n.nameSuffix), "nickname": opt(n.nickname),
            ]
            name = parts
        }
        let result: [String: Any] = [
            "user": c.user, "state": opt(c.state), "fullName": name, "email": opt(c.email),
            "realUserStatus": c.realUserStatus.rawValue, "identityToken": text(c.identityToken),
            "authorizationCode": text(c.authorizationCode),
        ]
        done(result, nil)
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithError error: Error) {
        let code: String
        switch (error as? ASAuthorizationError)?.code {
        case .canceled: code = "ERR_REQUEST_CANCELED"
        case .failed: code = "ERR_REQUEST_FAILED"
        case .invalidResponse: code = "ERR_INVALID_RESPONSE"
        case .notHandled: code = "ERR_REQUEST_NOT_HANDLED"
        case .notInteractive: code = "ERR_REQUEST_NOT_INTERACTIVE"
        default: code = "ERR_REQUEST_UNKNOWN"
        }
        done(nil, "\(code): \(error.localizedDescription)")
    }
}

/// Apple's own button. Its type and style are fixed when it is made, so a change of either makes a new one.
final class PxAppleAuthenticationButton: NSObject, PxNativeView {
    private let box = UIView()
    private let emit: (String, Any?) -> Void
    private var button: ASAuthorizationAppleIDButton?
    private var type = 0
    private var style = 2
    private var radius: CGFloat?

    var view: UIView { box }

    init(_ emit: @escaping (String, Any?) -> Void) {
        self.emit = emit
        super.init()
        box.backgroundColor = .clear
        rebuild()
    }

    func update(_ props: [String: Any], _ removed: [String]) {
        var changed = false
        if let t = (props["button_type"] as? NSNumber)?.intValue, t != type { type = t; changed = true }
        if let s = (props["button_style"] as? NSNumber)?.intValue, s != style { style = s; changed = true }
        if let r = props["corner_radius"] as? NSNumber { radius = CGFloat(r.doubleValue) }
        if removed.contains("corner_radius") { radius = nil }
        if changed { rebuild() } else { applyRadius() }
    }

    func dispose() {
        button?.removeTarget(nil, action: nil, for: .allEvents)
    }

    private func rebuild() {
        button?.removeFromSuperview()
        let kind: ASAuthorizationAppleIDButton.ButtonType
        switch type {
        case 1: kind = .continue
        case 2: kind = .signUp
        default: kind = .signIn
        }
        let look: ASAuthorizationAppleIDButton.Style
        switch style {
        case 0: look = .white
        case 1: look = .whiteOutline
        default: look = .black
        }
        let b = ASAuthorizationAppleIDButton(authorizationButtonType: kind, authorizationButtonStyle: look)
        b.frame = box.bounds
        b.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        b.addTarget(self, action: #selector(pressed), for: .touchUpInside)
        box.addSubview(b)
        button = b
        applyRadius()
    }

    private func applyRadius() {
        if let r = radius { button?.cornerRadius = r }
    }

    @objc private func pressed() { emit("press", nil) }
}
